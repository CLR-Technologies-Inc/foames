# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Agent Suggestions by status, grouped by category, severity or the agent that raised them, with
how long resolved ones took."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import get_datetime

from foames.foames_mes.kpi import resolution_hours
from foames.foames_mes.report.utils import chart_of, date_window, summary_item

STATUSES = ("Open", "Accepted", "Dismissed", "Done")
GROUPS = ("Category", "Severity", "Agent")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start, end = date_window(filters, days=90)
	group_by = filters.get("group_by") if filters.get("group_by") in GROUPS else "Category"
	field = group_by.lower()
	conditions = [["creation", ">=", start], ["creation", "<", end]]
	for name in ("category", "severity", "agent", "status"):
		if filters.get(name):
			conditions.append([name, "=", filters.get(name)])
	suggestions = frappe.get_all(
		"Agent Suggestion",
		filters=conditions,
		fields=["name", "category", "severity", "agent", "status", "creation", "resolved_on"],
	)

	groups = defaultdict(lambda: {status: 0 for status in STATUSES})
	pairs = defaultdict(list)
	for s in suggestions:
		key = s.get(field) or _("Not Specified")
		groups[key][s.status] = groups[key].get(s.status, 0) + 1
		if s.status != "Open" and s.resolved_on:
			pairs[key].append((get_datetime(s.creation), get_datetime(s.resolved_on)))

	rows = []
	for key, counts in sorted(groups.items(), key=lambda item: -sum(item[1].values())):
		total = sum(counts.values())
		res = resolution_hours(pairs[key])
		rows.append(
			{
				"group": key,
				"open": counts["Open"],
				"accepted": counts["Accepted"],
				"dismissed": counts["Dismissed"],
				"done": counts["Done"],
				"total": total,
				"acceptance": ((counts["Accepted"] + counts["Done"]) / total * 100) if total else 0,
				"median_hours": res["median_hours"],
			}
		)
	all_pairs = [p for ps in pairs.values() for p in ps]
	overall = resolution_hours(all_pairs)
	open_count = sum(r["open"] for r in rows)
	return (
		get_columns(group_by),
		rows,
		None,
		get_chart(rows),
		[
			summary_item(_("Open"), open_count, "Int", "Orange" if open_count else "Green"),
			summary_item(_("Raised"), len(suggestions), "Int"),
			summary_item(_("Median Hours to Resolve"), overall["median_hours"] or 0, "Float"),
		],
	)


def get_columns(group_by):
	return [
		{"fieldname": "group", "label": _(group_by), "fieldtype": "Data", "width": 160},
		{"fieldname": "open", "label": _("Open"), "fieldtype": "Int", "width": 80},
		{"fieldname": "accepted", "label": _("Accepted"), "fieldtype": "Int", "width": 90},
		{"fieldname": "done", "label": _("Done"), "fieldtype": "Int", "width": 80},
		{"fieldname": "dismissed", "label": _("Dismissed"), "fieldtype": "Int", "width": 90},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 80},
		{"fieldname": "acceptance", "label": _("Accepted or Done %"), "fieldtype": "Percent", "width": 140},
		{
			"fieldname": "median_hours",
			"label": _("Median Hours to Resolve"),
			"fieldtype": "Float",
			"width": 170,
		},
	]


def get_chart(rows):
	return chart_of(
		[str(r["group"]) for r in rows],
		[
			{"name": _("Open"), "values": [r["open"] for r in rows]},
			{"name": _("Accepted"), "values": [r["accepted"] for r in rows]},
			{"name": _("Done"), "values": [r["done"] for r in rows]},
			{"name": _("Dismissed"), "values": [r["dismissed"] for r in rows]},
		],
		"bar",
		colors=["#ffa00a", "#2490ef", "#29cd42", "#b8c2cc"],
		barOptions={"stacked": 1},
	)
