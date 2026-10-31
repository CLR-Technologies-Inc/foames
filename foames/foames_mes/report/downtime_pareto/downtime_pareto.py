# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Downtime minutes by reason, category or machine, largest first, with the running share.

Each Downtime Record is clipped to the date window, so a stoppage that straddles midnight on the
first day only counts the minutes inside the window. Records without a reason are reported as
Unclassified rather than dropped: the share of unexplained downtime is itself a finding.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes.kpi import clip_minutes, pareto
from foames.foames_mes.report.utils import chart_of, date_window, machines_in_scope, summary_item

GROUPS = {"Reason": "reason", "Category": "category", "Machine": "machine"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start, end = date_window(filters)
	group_by = filters.get("group_by") if filters.get("group_by") in GROUPS else "Reason"
	machines = machines_in_scope(filters)
	records = get_records(list(machines), start, end, include_open=bool(filters.get("include_open")))
	reasons = {
		r.name: r
		for r in frappe.get_all("Downtime Reason", fields=["name", "title", "category", "counts_as_planned"])
	}
	if not filters.get("include_planned"):
		records = [
			r for r in records if not (r.reason and reasons.get(r.reason, {}).get("counts_as_planned"))
		]

	now = now_datetime()
	rows = []
	for r in records:
		minutes = clip_minutes(
			get_datetime(r.start_time), get_datetime(r.end_time) if r.end_time else min(now, end), start, end
		)
		if minutes <= 0:
			continue
		reason = reasons.get(r.reason)
		if group_by == "Machine":
			label = r.machine
		elif group_by == "Category":
			label = reason.category if reason else None
		else:
			label = r.reason
		rows.append({"label": label, "minutes": minutes, "occurrences": 1})

	data = pareto(rows)
	for d in data:
		d["hours"] = d["minutes"] / 60.0
		if group_by == "Reason" and d["label"] in reasons:
			d["title"] = reasons[d["label"]].title
			d["category"] = reasons[d["label"]].category
	total = sum(d["minutes"] for d in data)
	unclassified = next((d["minutes"] for d in data if d["label"] == "Unclassified"), 0.0)
	return (
		get_columns(group_by),
		data,
		None,
		get_chart(data),
		[
			summary_item(_("Downtime (h)"), total / 60.0, "Float"),
			summary_item(_("Stoppages"), sum(d["occurrences"] for d in data), "Int"),
			summary_item(
				_("Unclassified"),
				(unclassified / total * 100) if total else 0,
				"Percent",
				"Red" if total and unclassified / total > 0.2 else "Green",
			),
		],
	)


def get_records(machine_names, start, end, include_open):
	if not machine_names:
		return []
	conditions = [
		["machine", "in", machine_names],
		["start_time", "<", end],
	]
	if not include_open:
		conditions.append(["status", "=", "Closed"])
	return frappe.get_all(
		"Downtime Record",
		filters=conditions,
		or_filters=[["end_time", "is", "not set"], ["end_time", ">", start]],
		fields=["name", "machine", "reason", "start_time", "end_time", "status"],
	)


def get_columns(group_by):
	first = {"fieldname": "label", "label": _(group_by), "fieldtype": "Data", "width": 160}
	if group_by == "Machine":
		first.update({"fieldtype": "Link", "options": "Machine"})
	elif group_by == "Reason":
		first.update({"fieldtype": "Link", "options": "Downtime Reason"})
	columns = [first]
	if group_by == "Reason":
		columns += [
			{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 160},
			{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 110},
		]
	columns += [
		{"fieldname": "minutes", "label": _("Minutes"), "fieldtype": "Float", "width": 100},
		{"fieldname": "hours", "label": _("Hours"), "fieldtype": "Float", "width": 90},
		{"fieldname": "occurrences", "label": _("Stoppages"), "fieldtype": "Int", "width": 90},
		{"fieldname": "share", "label": _("Share %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "cumulative_share", "label": _("Cumulative %"), "fieldtype": "Percent", "width": 110},
	]
	return columns


def get_chart(data):
	top = data[:12]
	return chart_of(
		[str(d["label"]) for d in top],
		[
			{"name": _("Minutes"), "chartType": "bar", "values": [round(d["minutes"], 1) for d in top]},
			{
				"name": _("Cumulative %"),
				"chartType": "line",
				"values": [round(d["cumulative_share"], 1) for d in top],
			},
		],
		"axis-mixed",
		colors=["#ff5858", "#2490ef"],
		barOptions={"spaceRatio": 0.4},
		lineOptions={"regionFill": 0},
	)
