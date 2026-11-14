# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Every failure chain across the PFMEAs a user can read, ranked by AIAG-VDA action priority, then
severity, occurrence and detection: the ratings, what the floor observed, and the state of each
action. Obsolete PFMEAs are left out unless one is chosen."""

import frappe
from frappe import _

from foames.foames_mes.pfmea import CLOSED_ACTION_STATUSES, has_action
from foames.foames_mes.report.utils import chart_of, summary_item

RANK = {"H": 0, "M": 1, "L": 2}
ROW_FIELDS = (
	"parent",
	"name",
	"idx",
	"op_no",
	"process_step",
	"machine",
	"function_requirement",
	"special_characteristic",
	"specification",
	"failure_effect",
	"severity",
	"failure_mode",
	"failure_cause",
	"prevention_controls",
	"occurrence",
	"detection_controls",
	"detection",
	"action_priority",
	"rpn",
	"measurement_name",
	"sample_size_frequency",
	"reaction_plan",
	"observed_occurrence",
	"observed_per_thousand",
	"spc_signals",
	"prevention_action",
	"detection_action",
	"responsible",
	"target_date",
	"action_status",
	"new_action_priority",
)


def pfmea_rows(filters) -> list[dict]:
	"""PFMEA Item rows of the PFMEAs in scope, in PFMEA then row order, with the PFMEA's title."""
	conditions = {}
	if filters.get("pfmea"):
		conditions["name"] = filters.pfmea
	else:
		conditions["status"] = ("!=", "Obsolete")
	if filters.get("process_line"):
		conditions["process_line"] = filters.process_line
	parents = {
		p.name: p
		for p in frappe.get_list(
			"PFMEA", filters=conditions, fields=["name", "title", "status"], order_by="name"
		)
	}
	if not parents:
		return []
	item_filters = {"parenttype": "PFMEA", "parentfield": "items", "parent": ("in", list(parents))}
	if filters.get("machine"):
		item_filters["machine"] = filters.machine
	rows = frappe.get_all(
		"PFMEA Item", filters=item_filters, fields=list(ROW_FIELDS), order_by="parent asc, idx asc"
	)
	for row in rows:
		row["pfmea"], row["row"] = row.pop("parent"), row.pop("name")
		row["pfmea_title"] = parents[row["pfmea"]].title
		row["pfmea_status"] = parents[row["pfmea"]].status
	return rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = pfmea_rows(filters)
	if filters.get("action_priority"):
		rows = [r for r in rows if r.get("action_priority") == filters.action_priority]
	if filters.get("open_actions_only"):
		rows = [r for r in rows if has_action(r) and r.get("action_status") not in CLOSED_ACTION_STATUSES]
	rows.sort(
		key=lambda r: (
			RANK.get(r.get("action_priority"), 3),
			-(r.get("severity") or 0),
			-(r.get("occurrence") or 0),
			-(r.get("detection") or 0),
		)
	)
	counts = {p: sum(1 for r in rows if r.get("action_priority") == p) for p in RANK}
	above = sum(
		1
		for r in rows
		if r.get("observed_occurrence") and r["observed_occurrence"] > (r.get("occurrence") or 10)
	)
	return (
		get_columns(),
		rows,
		None,
		chart_of(
			[_("High"), _("Medium"), _("Low")],
			[{"name": _("Failure Chains"), "values": [counts["H"], counts["M"], counts["L"]]}],
			colors=["#E24C4C"],
		)
		if rows
		else None,
		[
			summary_item(_("High"), counts["H"], "Int", "Red"),
			summary_item(_("Medium"), counts["M"], "Int", "Orange"),
			summary_item(_("Low"), counts["L"], "Int", "Green"),
			summary_item(_("Observed Above Rating"), above, "Int", "Red" if above else "Green"),
		],
	)


def get_columns():
	return [
		{"fieldname": "pfmea", "label": _("PFMEA"), "fieldtype": "Link", "options": "PFMEA", "width": 120},
		{"fieldname": "op_no", "label": _("Op"), "fieldtype": "Data", "width": 60},
		{"fieldname": "process_step", "label": _("Process Step"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "machine",
			"label": _("Machine"),
			"fieldtype": "Link",
			"options": "Machine",
			"width": 110,
		},
		{"fieldname": "failure_mode", "label": _("Failure Mode"), "fieldtype": "Data", "width": 160},
		{"fieldname": "failure_effect", "label": _("Effect"), "fieldtype": "Data", "width": 150},
		{"fieldname": "failure_cause", "label": _("Cause"), "fieldtype": "Data", "width": 150},
		{"fieldname": "severity", "label": _("S"), "fieldtype": "Int", "width": 50},
		{"fieldname": "occurrence", "label": _("O"), "fieldtype": "Int", "width": 50},
		{"fieldname": "detection", "label": _("D"), "fieldtype": "Int", "width": 50},
		{"fieldname": "action_priority", "label": _("AP"), "fieldtype": "Data", "width": 50},
		{"fieldname": "rpn", "label": _("RPN"), "fieldtype": "Int", "width": 60},
		{"fieldname": "observed_occurrence", "label": _("Observed O"), "fieldtype": "Int", "width": 90},
		{
			"fieldname": "observed_per_thousand",
			"label": _("Per Thousand"),
			"fieldtype": "Float",
			"width": 100,
		},
		{"fieldname": "spc_signals", "label": _("SPC Signals"), "fieldtype": "Int", "width": 90},
		{"fieldname": "action_status", "label": _("Action Status"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "responsible",
			"label": _("Responsible"),
			"fieldtype": "Link",
			"options": "User",
			"width": 140,
		},
		{"fieldname": "target_date", "label": _("Target Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "new_action_priority", "label": _("Revised AP"), "fieldtype": "Data", "width": 80},
	]
