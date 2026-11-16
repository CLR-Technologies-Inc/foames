# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""One row per commissioning package: how far it is, what blocks its handover and whether it is late."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from foames.foames_mes.report.utils import summary_item

SHOW = {
	"Open packages": ("Planning", "In Progress", "Ready for Handover"),
	"All packages": ("Planning", "In Progress", "Ready for Handover", "Handed Over", "Cancelled"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = status_rows(filters, getdate(nowdate()))
	return (
		get_columns(),
		rows,
		None,
		None,
		[
			summary_item(_("Packages"), len(rows), "Int", "Blue"),
			summary_item(
				_("Ready for Handover"),
				sum(1 for r in rows if r["status"] == "Ready for Handover"),
				"Int",
				"Green",
			),
			summary_item(_("Late"), sum(1 for r in rows if r["late"]), "Int", "Red"),
		],
	)


def status_rows(filters, today) -> list[dict]:
	conditions = {"status": ("in", SHOW.get(filters.get("show") or "Open packages", SHOW["Open packages"]))}
	if filters.get("line"):
		conditions["line"] = filters.line
	rows = []
	for pkg in frappe.get_list(
		"Commissioning Package",
		filters=conditions,
		fields=[
			"name",
			"title",
			"line",
			"status",
			"percent_complete",
			"tests_passed",
			"loop_checks_passed",
			"open_punch_a",
			"open_punch_b",
			"open_punch_c",
			"blocker_count",
			"planned_handover",
			"handed_over_on",
			"commissioning_lead",
		],
		order_by="planned_handover asc, name asc",
	):
		late = bool(
			pkg.status not in ("Handed Over", "Cancelled")
			and pkg.planned_handover
			and getdate(pkg.planned_handover) < today
		)
		rows.append({**pkg, "late": 1 if late else 0})
	return rows


def get_columns():
	return [
		{
			"fieldname": "name",
			"label": _("Package"),
			"fieldtype": "Link",
			"options": "Commissioning Package",
			"width": 130,
		},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 200},
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "percent_complete", "label": _("Complete"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "tests_passed", "label": _("Tests Passed"), "fieldtype": "Data", "width": 110},
		{"fieldname": "loop_checks_passed", "label": _("Loops Passed"), "fieldtype": "Data", "width": 110},
		{"fieldname": "open_punch_a", "label": _("Open A"), "fieldtype": "Int", "width": 80},
		{"fieldname": "open_punch_b", "label": _("Open B"), "fieldtype": "Int", "width": 80},
		{"fieldname": "open_punch_c", "label": _("Open C"), "fieldtype": "Int", "width": 80},
		{"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
		{"fieldname": "planned_handover", "label": _("Planned Handover"), "fieldtype": "Date", "width": 130},
		{"fieldname": "late", "label": _("Late"), "fieldtype": "Check", "width": 70},
		{"fieldname": "handed_over_on", "label": _("Handed Over"), "fieldtype": "Datetime", "width": 150},
		{
			"fieldname": "commissioning_lead",
			"label": _("Lead"),
			"fieldtype": "Link",
			"options": "User",
			"width": 150,
		},
	]
