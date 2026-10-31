# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The floor snapshot: one plain dict describing the plant right now.

The visual floor page renders it, the built-in rules read it, and external agents fetch it
through the API. Everything an agent needs to reason about the floor is in here, so an agent
never has to query DocTypes one by one.

Other apps add their own sections through the `foames_floor_snapshot_extensions` hook: each
dotted path is called with the snapshot dict, the start of the window and the current time, and
adds keys to the dict in place.
"""

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, get_datetime, now_datetime

from foames.foames_mes.counters import minutes_between


def floor_snapshot(days: int = 1) -> dict:
	now = now_datetime()
	since = add_days(now, -days)
	machines = frappe.get_all(
		"Machine",
		{"disabled": 0},
		[
			"name",
			"title",
			"status",
			"last_seen",
			"last_count_at",
			"machine_type",
			"ideal_cycle_seconds",
			"current_job_reference",
			"current_job_since",
		],
		order_by="name",
	)
	jobs = current_jobs([m.current_job_reference for m in machines if m.current_job_reference])
	for m in machines:
		m["current_job"] = jobs.get(m.pop("current_job_reference"))
		if m["current_job"]:
			m["current_job"]["since"] = m.current_job_since
		m.pop("current_job_since")
		# Measured from the machine's latest count ever (kept on the Machine by event processing), not
		# only inside the window, so a machine that counted yesterday and reports Running without
		# counting today is still caught by the rules.
		last_count_at = m.pop("last_count_at")
		m["minutes_since_count"] = (
			minutes_between(get_datetime(last_count_at), now) if last_count_at else None
		)
		m["counts"] = counts_since(m.name, since)
		m["oee_today"] = frappe.db.get_value(
			"OEE Period",
			{"machine": m.name},
			["oee", "availability", "performance", "quality"],
			as_dict=True,
			order_by="from_time desc",
		)
	downtime = []
	period = f"{since:%Y-%m-%d} to {now:%Y-%m-%d}"
	for m in machines:
		by_reason = downtime_by_reason(m.name, since, now)
		classified = {reason: minutes for reason, minutes in by_reason.items() if reason}
		if classified:
			top_reason, top_minutes = max(classified.items(), key=lambda item: item[1])
			downtime.append(
				{
					"machine": m.name,
					"period": period,
					"total_minutes": sum(by_reason.values()),
					"unclassified_minutes": by_reason.get(None, 0),
					"top_reason": top_reason,
					"top_minutes": top_minutes,
				}
			)
	references = (
		frappe.get_all(
			"External Reference", {"status": "Missing"}, ["name", "reference_type", "external_id", "status"]
		)
		if frappe.has_permission("External Reference", "read")
		else []
	)
	snapshot = {
		"as_of": now,
		"machines": machines,
		"downtime_by_machine": downtime,
		"external_references": references,
		"open_suggestions": frappe.get_all(
			"Agent Suggestion",
			{"status": "Open"},
			["name", "title", "category", "severity", "agent", "reference_doctype", "reference_name"],
		),
	}
	for extension in frappe.get_hooks("foames_floor_snapshot_extensions") or []:
		frappe.get_attr(extension)(snapshot, since, now)
	return snapshot


def current_jobs(references: list[str]) -> dict[str, dict]:
	"""External Reference name -> {reference, erp_system, external_id, label, status} for the jobs
	machines are working on."""
	if not references:
		return {}
	return {
		r.name: {
			"reference": r.name,
			"erp_system": r.erp_system,
			"external_id": r.external_id,
			"label": r.label,
			"status": r.status,
		}
		for r in frappe.get_all(
			"External Reference",
			{"name": ("in", references)},
			["name", "erp_system", "external_id", "label", "status"],
		)
	}


def downtime_by_reason(
	machine: str, since, until, ignore_permissions: bool = True
) -> dict[str | None, float]:
	"""Minutes of downtime per reason inside [since, until), counting the part of each record that
	overlaps the window. Open downtime counts up to `until`. Downtime with no reason assigned yet is
	returned under the key None, so shares are computed over all downtime, not only the classified part.

	The snapshot and the rules read every record. A read on behalf of a user (the MCP tools) passes
	`ignore_permissions=False`, so that user's role and user permissions filter the records."""
	rows = frappe.get_list(
		"Downtime Record",
		filters=[
			["machine", "=", machine],
			["start_time", "<", until],
		],
		or_filters=[["end_time", "is", "not set"], ["end_time", ">=", since]],
		fields=["reason", "start_time", "end_time"],
		ignore_permissions=ignore_permissions,
	)
	minutes: dict[str, float] = {}
	for r in rows:
		start = max(get_datetime(r.start_time), since)
		end = min(get_datetime(r.end_time), until) if r.end_time else until
		if end > start:
			minutes[r.reason] = minutes.get(r.reason, 0) + minutes_between(start, end)
	return minutes


def counts_since(machine: str, since) -> dict[str, float]:
	"""Counter deltas per counter name since `since`, for example {"good": 120, "scrap": 3}."""
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.counter_name, Sum(event.delta).as_("total"))
		.where((event.machine == machine) & (event.event_type == "Count") & (event.timestamp >= since))
		.groupby(event.counter_name)
		.run(as_dict=True)
	)
	return {r.counter_name: r.total or 0 for r in rows}


def collect_findings(snapshot: dict) -> list[dict]:
	"""The built-in rules plus every rule registered through the `foames_suggestion_rules` hook."""
	from foames.foames_mes.suggestions import all_rules

	findings = all_rules(snapshot)
	for rule in frappe.get_hooks("foames_suggestion_rules") or []:
		findings.extend(frappe.get_attr(rule)(snapshot))
	return findings
