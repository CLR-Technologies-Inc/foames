# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The punch list: commissioning punch items by category, with what blocks handover and what is
overdue. Open items are shown by default, category A first, then the oldest due date."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate

from foames.foames_commissioning.commissioning import PUNCH_CATEGORIES, PUNCH_OPEN, punch_blocks_handover
from foames.foames_mes.report.utils import chart_of, summary_item

SHOW = {
	"Open items": PUNCH_OPEN,
	"Closed items": ("Closed",),
	"All items": ("Open", "Ready for Verification", "Closed", "Cancelled"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = punch_rows(filters, getdate(nowdate()))
	open_rows = [r for r in rows if r["status"] in PUNCH_OPEN]
	by_category = {c: sum(1 for r in open_rows if r["category"] == c) for c in PUNCH_CATEGORIES}
	return (
		get_columns(),
		rows,
		None,
		chart_of(
			[_("Category {0}").format(c) for c in PUNCH_CATEGORIES],
			[{"name": _("Open"), "values": [by_category[c] for c in PUNCH_CATEGORIES]}],
			colors=["#FF5858"],
		)
		if open_rows
		else None,
		[
			summary_item(_("Open A"), by_category["A"], "Int", "Red"),
			summary_item(_("Open B"), by_category["B"], "Int", "Orange"),
			summary_item(_("Open C"), by_category["C"], "Int", "Blue"),
			summary_item(_("Blocking Handover"), sum(1 for r in rows if r["blocks_handover"]), "Int", "Red"),
			summary_item(_("Overdue"), sum(1 for r in rows if r["overdue"]), "Int", "Orange"),
		],
	)


def punch_rows(filters, today) -> list[dict]:
	conditions = {"status": ("in", SHOW.get(filters.get("show") or "Open items", PUNCH_OPEN))}
	for field in ("package", "category", "assigned_to", "equipment_tag"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	rows = []
	for item in frappe.get_list(
		"Punch Item",
		filters=conditions,
		fields=[
			"name",
			"package",
			"title",
			"category",
			"status",
			"equipment_tag",
			"assigned_to",
			"due_on",
			"deferred",
			"raised_on",
			"closed_on",
		],
		order_by="name",
	):
		overdue = bool(item.status in PUNCH_OPEN and item.due_on and getdate(item.due_on) < today)
		if filters.get("overdue_only") and not overdue:
			continue
		rows.append(
			{
				**item,
				"blocks_handover": 1 if punch_blocks_handover(item) else 0,
				"overdue": 1 if overdue else 0,
				"days_open": date_diff(item.closed_on or today, item.raised_on) if item.raised_on else None,
			}
		)
	rows.sort(key=lambda r: (r["category"], str(r["due_on"] or "9999-12-31"), r["name"]))
	return rows


def get_columns():
	return [
		{
			"fieldname": "name",
			"label": _("Punch Item"),
			"fieldtype": "Link",
			"options": "Punch Item",
			"width": 130,
		},
		{"fieldname": "category", "label": _("Cat."), "fieldtype": "Data", "width": 60},
		{"fieldname": "title", "label": _("Description"), "fieldtype": "Data", "width": 260},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "package",
			"label": _("Package"),
			"fieldtype": "Link",
			"options": "Commissioning Package",
			"width": 130,
		},
		{"fieldname": "equipment_tag", "label": _("Equipment"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "assigned_to",
			"label": _("Assigned To"),
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"fieldname": "due_on", "label": _("Due On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "overdue", "label": _("Overdue"), "fieldtype": "Check", "width": 80},
		{"fieldname": "deferred", "label": _("Deferred"), "fieldtype": "Check", "width": 80},
		{"fieldname": "blocks_handover", "label": _("Blocks Handover"), "fieldtype": "Check", "width": 120},
		{"fieldname": "days_open", "label": _("Days Open"), "fieldtype": "Int", "width": 90},
	]
