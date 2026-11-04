# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Every enabled Maintenance Plan with its meter read now: what is overdue, due, or coming due.

The meters are read live, not from the values the hourly check stored, so the list is current when
it is opened. Plans are ordered worst first, then by how far through their interval they are.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

from foames.foames_mes.maintenance import STATUSES, UNITS
from foames.foames_mes.report.utils import chart_of, machines_in_scope, summary_item

RANK = {status: index for index, status in enumerate(STATUSES)}
SHOW = {
	"Due Soon or later": ("Due Soon", "Due", "Overdue"),
	"Due or Overdue": ("Due", "Overdue"),
	"All plans": STATUSES,
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	machines = machines_in_scope(filters)
	rows = due_rows(filters, machines, now_datetime())
	counts = {status: sum(1 for r in rows if r["status"] == status) for status in STATUSES}
	return (
		get_columns(),
		rows,
		None,
		chart_of(
			[_(s) for s in STATUSES[1:]],
			[{"name": _("Plans"), "values": [counts[s] for s in STATUSES[1:]]}],
			colors=["#ECAD4B"],
		)
		if rows
		else None,
		[
			summary_item(_("Overdue"), counts["Overdue"], "Int", "Red"),
			summary_item(_("Due"), counts["Due"], "Int", "Orange"),
			summary_item(_("Due Soon"), counts["Due Soon"], "Int", "Yellow"),
		],
	)


def due_rows(filters, machines: dict, now) -> list[dict]:
	if not machines:
		return []
	conditions = {"disabled": 0, "machine": ("in", list(machines))}
	if filters.get("trigger"):
		conditions["trigger_type"] = filters.trigger
	show = SHOW.get(filters.get("show") or "Due Soon or later", SHOW["Due Soon or later"])
	horizon = add_days(now, int(filters.get("horizon_days") or 0)) if filters.get("horizon_days") else None
	rows = []
	for name in frappe.get_list("Maintenance Plan", filters=conditions, pluck="name", order_by="name"):
		plan = frappe.get_doc("Maintenance Plan", name)
		meter = plan.measure(now)
		due_on = meter["due_on"]
		within_horizon = bool(horizon and due_on and get_datetime(due_on) <= horizon)
		if meter["status"] not in show and not within_horizon:
			continue
		rows.append(
			{
				"maintenance_plan": name,
				"title": plan.title,
				"machine": plan.machine,
				"line": machines[plan.machine].line,
				"trigger": plan.trigger_type,
				"unit": UNITS.get(plan.trigger_type),
				"interval": plan.interval,
				"used": meter["used"],
				"remaining": meter["remaining"],
				"percent_used": meter["percent"],
				"status": meter["status"],
				"due_on": due_on,
				"last_done_on": meter["since"],
				"open_work_order": meter["open_work_order"],
				"estimated_minutes": plan.estimated_minutes,
			}
		)
	rows.sort(key=lambda r: (-RANK[r["status"]], -(r["percent_used"] or 0), r["maintenance_plan"]))
	return rows


def get_columns():
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "maintenance_plan",
			"label": _("Plan"),
			"fieldtype": "Link",
			"options": "Maintenance Plan",
			"width": 120,
		},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "machine",
			"label": _("Machine"),
			"fieldtype": "Link",
			"options": "Machine",
			"width": 120,
		},
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 90},
		{"fieldname": "trigger", "label": _("Trigger"), "fieldtype": "Data", "width": 90},
		{"fieldname": "percent_used", "label": _("Used (%)"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "used", "label": _("Used"), "fieldtype": "Float", "precision": 1, "width": 90},
		{"fieldname": "interval", "label": _("Interval"), "fieldtype": "Float", "precision": 1, "width": 90},
		{
			"fieldname": "remaining",
			"label": _("Remaining"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 100,
		},
		{"fieldname": "unit", "label": _("Unit"), "fieldtype": "Data", "width": 90},
		{"fieldname": "due_on", "label": _("Due On"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "last_done_on", "label": _("Last Service"), "fieldtype": "Datetime", "width": 150},
		{
			"fieldname": "open_work_order",
			"label": _("Open Work Order"),
			"fieldtype": "Link",
			"options": "Maintenance Work Order",
			"width": 140,
		},
		{"fieldname": "estimated_minutes", "label": _("Est. Minutes"), "fieldtype": "Float", "width": 100},
	]
