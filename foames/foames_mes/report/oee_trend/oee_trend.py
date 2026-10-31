# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OEE over time, one row per machine (or line) and day, rolled up from the stored OEE Periods.

The trend never recomputes OEE: it reads the periods the daily task created, so what the report
shows is what the OEE Period list shows. Lines are the Machine's Line field; a line's figures are
the time-weighted roll-up of its machines, never an average of their percentages.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import getdate

from foames.foames_mes.kpi import roll_up_oee
from foames.foames_mes.report.utils import (
	MAX_SERIES,
	chart_of,
	date_window,
	machines_in_scope,
	summary_item,
)

METRICS = ("OEE", "Availability", "Performance", "Quality")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start, end = date_window(filters)
	group_by = filters.get("group_by") or "Machine"
	metric = filters.get("metric") if filters.get("metric") in METRICS else "OEE"
	machines = machines_in_scope(filters)
	periods = get_periods(list(machines), start, end)

	grouped = defaultdict(list)
	for p in periods:
		day = getdate(p.from_time)
		if group_by == "Line":
			key = machines[p.machine].line or _("No Line")
		elif group_by == "Day":
			key = _("All Machines")
		else:
			key = p.machine
		grouped[(key, day)].append(p)

	rows = []
	for (key, day), group in sorted(grouped.items(), key=lambda item: (str(item[0][1]), item[0][0])):
		roll = roll_up_oee(group)
		row = {"group": key, "day": day, **roll}
		if group_by == "Machine":
			row["machine"] = key
			row["line"] = machines[key].line
		rows.append(row)

	overall = roll_up_oee(periods)
	return (
		get_columns(group_by),
		rows,
		None,
		get_chart(rows, metric.lower()),
		get_summary(overall, len(machines)),
	)


def get_periods(machine_names, start, end):
	if not machine_names:
		return []
	return frappe.get_all(
		"OEE Period",
		filters=[
			["machine", "in", machine_names],
			["from_time", ">=", start],
			["from_time", "<", end],
		],
		fields=[
			"name",
			"machine",
			"from_time",
			"to_time",
			"planned_minutes",
			"ideal_cycle_seconds",
			"run_minutes",
			"planned_downtime_minutes",
			"unplanned_downtime_minutes",
			"unknown_minutes",
			"good_count",
			"scrap_count",
			"availability",
			"performance",
			"quality",
			"oee",
		],
		order_by="from_time asc, machine asc",
	)


def get_columns(group_by):
	columns = [{"fieldname": "day", "label": _("Day"), "fieldtype": "Date", "width": 100}]
	if group_by == "Machine":
		columns += [
			{
				"fieldname": "machine",
				"label": _("Machine"),
				"fieldtype": "Link",
				"options": "Machine",
				"width": 140,
			},
			{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 100},
		]
	else:
		columns.append({"fieldname": "group", "label": _(group_by), "fieldtype": "Data", "width": 140})
	columns += [
		{"fieldname": "oee", "label": _("OEE %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "availability", "label": _("Availability %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "performance", "label": _("Performance %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "quality", "label": _("Quality %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "planned_minutes", "label": _("Planned (min)"), "fieldtype": "Float", "width": 100},
		{"fieldname": "run_minutes", "label": _("Run (min)"), "fieldtype": "Float", "width": 90},
		{
			"fieldname": "unplanned_downtime_minutes",
			"label": _("Unplanned Down (min)"),
			"fieldtype": "Float",
			"width": 130,
		},
		{"fieldname": "unknown_minutes", "label": _("Unknown (min)"), "fieldtype": "Float", "width": 110},
		{"fieldname": "good_count", "label": _("Good"), "fieldtype": "Float", "width": 80},
		{"fieldname": "scrap_count", "label": _("Scrap"), "fieldtype": "Float", "width": 80},
		{"fieldname": "periods", "label": _("Periods"), "fieldtype": "Int", "width": 70},
	]
	return columns


def get_chart(rows, metric):
	"""One line per group across the days in the window; the busiest groups when there are many."""
	days = sorted({str(r["day"]) for r in rows})
	by_group = defaultdict(dict)
	weight = defaultdict(float)
	for r in rows:
		by_group[r["group"]][str(r["day"])] = round(r[metric], 1)
		weight[r["group"]] += r["planned_minutes"]
	groups = sorted(by_group, key=lambda g: weight[g], reverse=True)[:MAX_SERIES]
	datasets = [
		{"name": str(g), "values": [by_group[g].get(day) for day in days]} for g in sorted(groups, key=str)
	]
	return chart_of(
		days,
		datasets,
		"line",
		colors=["#2490ef", "#29cd42", "#ffa00a", "#ff5858", "#743ee2", "#1f9ba6", "#b554ff", "#ff6b9d"],
		lineOptions={"regionFill": 0, "hideDots": 1},
		axisOptions={"xIsSeries": 1, "shortenYAxisNumbers": 1},
	)


def get_summary(overall, machine_count):
	def colour(value):
		return "Green" if value >= 85 else "Orange" if value >= 60 else "Red"

	return [
		summary_item(_("OEE"), overall["oee"], "Percent", colour(overall["oee"])),
		summary_item(_("Availability"), overall["availability"], "Percent"),
		summary_item(_("Performance"), overall["performance"], "Percent"),
		summary_item(_("Quality"), overall["quality"], "Percent"),
		summary_item(_("Machines"), machine_count, "Int"),
	]
