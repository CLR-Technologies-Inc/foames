# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Control charts over Measurement-type Machine Events, on a Frappe site.

The arithmetic and the run rules live in `foames.foames_mes.spc`, which has no Frappe dependency;
this module reads the readings, applies the settings in Machine Data Settings and decides which
findings become Agent Suggestions. `collect_findings` in `floor.py` calls `spc_findings` on every
suggestion run, so SPC signals arrive through the same path as the other built-in rules.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from foames.foames_mes import spc

SETTINGS_DEFAULTS = {
	"spc_enabled": 1,
	"spc_rule_set": "Nelson",
	"spc_subgroup_size": 0,
	"spc_baseline_days": 7,
	"spc_recent_hours": 2,
	"spc_min_baseline_points": spc.MIN_BASELINE_POINTS,
}


def spc_settings() -> frappe._dict:
	"""The SPC settings, with the defaults for any value never saved (a site that saved Machine Data
	Settings before these fields existed has no row for them)."""
	stored = frappe.db.get_singles_dict("Machine Data Settings", cast=False) or {}
	out = frappe._dict()
	for key, default in SETTINGS_DEFAULTS.items():
		value = stored.get(key)
		out[key] = default if value in (None, "") else value
	out.spc_enabled = cint(out.spc_enabled)
	out.spc_subgroup_size = cint(out.spc_subgroup_size)
	out.spc_baseline_days = max(cint(out.spc_baseline_days), 1)
	out.spc_recent_hours = max(cint(out.spc_recent_hours), 1)
	out.spc_min_baseline_points = max(cint(out.spc_min_baseline_points), 2)
	if out.spc_rule_set not in spc.RULE_SETS:
		out.spc_rule_set = "Nelson"
	return out


def measurement_series(machine: str, measurement: str, since, until=None) -> list[tuple]:
	"""[(timestamp, value)] of one machine measurement in time order, from `since` up to `until`."""
	event = frappe.qb.DocType("Machine Event")
	condition = (
		(event.machine == machine)
		& (event.event_type == "Measurement")
		& (event.measurement_name == measurement)
		& (event.timestamp >= since)
		& event.value.isnotnull()
	)
	if until is not None:
		condition &= event.timestamp < until
	rows = (
		frappe.qb.from_(event)
		.select(event.timestamp, event.value)
		.where(condition)
		.orderby(event.timestamp)
		.orderby(event.creation)
		.run()
	)
	return [(get_datetime(t), float(v)) for t, v in rows]


def measured_pairs(since) -> list[tuple[str, str]]:
	"""(machine, measurement) pairs with a Measurement event since `since`."""
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.machine, event.measurement_name)
		.distinct()
		.where(
			(event.event_type == "Measurement")
			& (event.timestamp >= since)
			& event.measurement_name.isnotnull()
			& (event.measurement_name != "")
		)
		.run()
	)
	return sorted((m, name) for m, name in rows)


def spc_findings(now=None) -> list[dict]:
	"""Findings for every measurement with readings in the recent window, judged against limits from
	the baseline window before it. A finding whose suggestion was resolved after its latest signal
	is dropped, so dismissing a signal sticks until the process signals again."""
	settings = spc_settings()
	if not settings.spc_enabled:
		return []
	now = get_datetime(now) if now else now_datetime()
	recent_from = add_to_date(now, hours=-settings.spc_recent_hours)
	since = add_to_date(recent_from, days=-settings.spc_baseline_days)
	out = []
	for machine, measurement in measured_pairs(recent_from):
		readings = measurement_series(machine, measurement, since)
		out.extend(
			spc.findings(
				{"machine": machine, "measurement": measurement, "readings": readings},
				recent_from=recent_from,
				rules=settings.spc_rule_set,
				subgroup_size=settings.spc_subgroup_size,
				min_baseline=settings.spc_min_baseline_points,
			)
		)
	return [f for f in out if not _resolved_since_signal(f)]


def _resolved_since_signal(finding: dict) -> bool:
	resolved_on = frappe.db.get_value(
		"Agent Suggestion",
		{"rule_key": finding["rule_key"], "status": ("!=", "Open")},
		"resolved_on",
	)
	if not resolved_on:
		return False
	return get_datetime(resolved_on) >= get_datetime(finding["evidence"]["latest_signal_at"])


@frappe.whitelist()
def get_control_chart(
	machine: str,
	measurement: str,
	from_date=None,
	to_date=None,
	chart: str = "I-MR",
	subgroup_size: int = spc.DEFAULT_SUBGROUP_SIZE,
	baseline_points: int = 0,
	rules: str = "Nelson",
) -> dict:
	"""A control chart of one machine measurement as JSON, for external agents and dashboards:
	{"chart", "points": [{"at", "value"}], "cl", "ucl", "lcl", "signals", "sigma_within",
	"secondary": the MR or R chart}. `baseline_points` 0 takes limits from every reading."""
	frappe.has_permission("Machine Event", "read", throw=True)
	return chart_data(
		machine,
		measurement,
		from_date,
		to_date,
		chart=chart,
		subgroup_size=cint(subgroup_size),
		baseline_points=cint(baseline_points),
		rules=rules,
	)


def chart_data(
	machine,
	measurement,
	from_date=None,
	to_date=None,
	chart="I-MR",
	subgroup_size=spc.DEFAULT_SUBGROUP_SIZE,
	baseline_points=0,
	rules="Nelson",
) -> dict:
	since = get_datetime(from_date) if from_date else add_to_date(now_datetime(), days=-7)
	until = get_datetime(to_date) if to_date else None
	readings = measurement_series(machine, measurement, since, until)
	values = [v for _, v in readings]
	times = [t for t, _ in readings]
	base = baseline_points or None
	empty = {"chart": chart, "points": [], "signals": [], "readings": len(readings)}
	if chart == "X-bar R":
		size = cint(subgroup_size)
		groups = spc.subgroups_of(values, size) if 2 <= size <= spc.MAX_SUBGROUP_SIZE else []
		if not groups:
			return {**empty, "message": "Not enough readings for one subgroup"}
		result = spc.xbar_r_chart(groups, baseline=max(base // size, 1) if base else None, rules=rules)
		labels = [times[(k + 1) * size - 1] for k in range(len(groups))]
		primary, secondary, secondary_labels = result["xbar"], result["range"], labels
	else:
		if len(values) < 2:
			return {**empty, "message": "An I-MR chart needs at least two readings"}
		result = spc.imr_chart(values, baseline=base, rules=rules)
		labels = times
		primary, secondary, secondary_labels = result["individuals"], result["moving_range"], times[1:]

	def shape(c, at):
		return {
			"chart": c["chart"],
			"points": [{"at": str(t), "value": v} for t, v in zip(at, c["points"], strict=True)],
			"cl": c["cl"],
			"ucl": c["ucl"],
			"lcl": c["lcl"],
			"signals": [{**s, "at": str(at[s["index"]])} for s in c["signals"]],
		}

	return {
		**shape(primary, labels),
		"secondary": shape(secondary, secondary_labels),
		"sigma_within": result["sigma_within"],
		"baseline_points": result["baseline_points"],
		"readings": len(readings),
		"subgroup_size": cint(subgroup_size) if chart == "X-bar R" else 1,
	}
