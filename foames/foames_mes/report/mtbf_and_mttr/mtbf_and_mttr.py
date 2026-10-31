# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Mean time between failures and mean time to repair, per machine, from the Downtime Records.

A failure is a closed, unplanned stoppage: a Downtime Record whose reason does not count as planned
(records without a reason are unplanned until someone says otherwise). MTBF uses the calendar window
less the downtime as operating time, which is the usual plant convention when a machine has no
scheduled calendar; the Scheduled Minutes Per Day on the Machine refines it when set.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime

from foames.foames_mes.kpi import clip_minutes, reliability
from foames.foames_mes.report.utils import chart_of, date_window, machines_in_scope, summary_item


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start, end = date_window(filters)
	machines = machines_in_scope(filters)
	window_days = (end - start).total_seconds() / 86400.0
	schedule = {
		m.name: m.scheduled_minutes_per_day
		for m in frappe.get_all(
			"Machine", {"name": ("in", list(machines) or [""])}, ["name", "scheduled_minutes_per_day"]
		)
	}
	planned_reasons = {r.name for r in frappe.get_all("Downtime Reason", {"counts_as_planned": 1}, ["name"])}
	breakdown_reasons = {
		r.name for r in frappe.get_all("Downtime Reason", {"category": "Breakdown"}, ["name"])
	}
	records = (
		frappe.get_all(
			"Downtime Record",
			filters=[
				["machine", "in", list(machines)],
				["status", "=", "Closed"],
				["start_time", "<", end],
				["end_time", ">", start],
			],
			fields=["machine", "reason", "start_time", "end_time"],
		)
		if machines
		else []
	)
	only_breakdowns = bool(filters.get("breakdowns_only"))

	per_machine = {name: {"failures": 0, "downtime": 0.0, "longest": 0.0} for name in machines}
	for r in records:
		if r.reason in planned_reasons:
			continue
		if only_breakdowns and r.reason not in breakdown_reasons:
			continue
		minutes = clip_minutes(get_datetime(r.start_time), get_datetime(r.end_time), start, end)
		if minutes <= 0:
			continue
		entry = per_machine[r.machine]
		entry["failures"] += 1
		entry["downtime"] += minutes
		entry["longest"] = max(entry["longest"], minutes)

	rows = []
	for name, entry in per_machine.items():
		per_day = schedule.get(name) or 1440
		window_minutes = min(per_day, 1440) * window_days
		stats = reliability(entry["failures"], entry["downtime"], window_minutes)
		rows.append(
			{
				"machine": name,
				"line": machines[name].line,
				"failures": stats["failures"],
				"downtime_hours": stats["downtime_minutes"] / 60.0,
				"mtbf_hours": (stats["mtbf_minutes"] / 60.0) if stats["mtbf_minutes"] is not None else None,
				"mttr_minutes": stats["mttr_minutes"],
				"longest_minutes": entry["longest"],
				"availability": stats["availability"],
				"window_hours": window_minutes / 60.0,
			}
		)
	rows.sort(key=lambda r: (-(r["failures"]), r["machine"]))

	total_failures = sum(r["failures"] for r in rows)
	total_down = sum(r["downtime_hours"] for r in rows)
	fleet = reliability(total_failures, total_down * 60.0, sum(r["window_hours"] for r in rows) * 60.0)
	return (
		get_columns(),
		rows,
		None,
		get_chart(rows),
		[
			summary_item(_("Failures"), total_failures, "Int"),
			summary_item(
				_("Fleet MTBF (h)"),
				(fleet["mtbf_minutes"] / 60.0) if fleet["mtbf_minutes"] is not None else 0,
				"Float",
			),
			summary_item(_("Fleet MTTR (min)"), fleet["mttr_minutes"], "Float"),
			summary_item(_("Inherent Availability"), fleet["availability"], "Percent"),
		],
	)


def get_columns():
	return [
		{
			"fieldname": "machine",
			"label": _("Machine"),
			"fieldtype": "Link",
			"options": "Machine",
			"width": 140,
		},
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 100},
		{"fieldname": "failures", "label": _("Failures"), "fieldtype": "Int", "width": 80},
		{"fieldname": "mtbf_hours", "label": _("MTBF (h)"), "fieldtype": "Float", "width": 100},
		{"fieldname": "mttr_minutes", "label": _("MTTR (min)"), "fieldtype": "Float", "width": 100},
		{"fieldname": "downtime_hours", "label": _("Downtime (h)"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "longest_minutes",
			"label": _("Longest Stop (min)"),
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"fieldname": "availability",
			"label": _("Inherent Availability %"),
			"fieldtype": "Percent",
			"width": 160,
		},
		{"fieldname": "window_hours", "label": _("Operating Window (h)"), "fieldtype": "Float", "width": 150},
	]


def get_chart(rows):
	shown = [r for r in rows if r["failures"]][:12]
	return chart_of(
		[r["machine"] for r in shown],
		[
			{"name": _("MTBF (h)"), "values": [round(r["mtbf_hours"] or 0, 1) for r in shown]},
			{"name": _("MTTR (h)"), "values": [round(r["mttr_minutes"] / 60.0, 2) for r in shown]},
		],
		"bar",
		colors=["#29cd42", "#ff5858"],
		barOptions={"spaceRatio": 0.5},
	)
