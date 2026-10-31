# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One view of both posting outboxes: how many postings sit in each status per adapter, how old the
oldest unposted one is, and what the last errors say.

The ERPNext and S/4HANA outboxes are separate DocTypes with the same lifecycle, so the report reads
whichever adapters are installed on the site and stacks them side by side.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes.report.utils import chart_of, date_window, summary_item

OUTBOXES = (("ERPNext", "ERPNext Outbox"), ("S/4HANA", "S4HANA Outbox"))
STATUSES = ("Queued", "Sending", "Retry", "Unknown", "Failed", "Posted", "Cancelled")
ATTENTION = ("Retry", "Unknown", "Failed")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start, end = date_window(filters, days=7)
	now = now_datetime()
	rows, failed_total, waiting_total, oldest_wait = [], 0, 0, 0.0
	for adapter, doctype in OUTBOXES:
		if not frappe.db.table_exists(doctype):
			continue
		if filters.get("adapter") and filters.get("adapter") != adapter:
			continue
		if not frappe.has_permission(doctype, "read"):
			continue
		conditions = [["creation", ">=", start], ["creation", "<", end]]
		if filters.get("operation"):
			conditions.append(["operation", "=", filters.get("operation")])
		postings = frappe.get_all(
			doctype,
			filters=conditions,
			fields=["name", "status", "operation", "attempts", "creation", "next_attempt_at", "last_error"],
		)
		# Unposted work outside the window still needs attention, so it is read without the window.
		backlog_conditions = [["status", "in", ("Queued", "Sending", "Retry", "Unknown", "Failed")]]
		if filters.get("operation"):
			backlog_conditions.append(["operation", "=", filters.get("operation")])
		backlog = frappe.get_all(
			doctype,
			filters=backlog_conditions,
			fields=["name", "status", "operation", "attempts", "creation", "next_attempt_at", "last_error"],
		)
		seen = {p.name for p in postings}
		postings += [p for p in backlog if p.name not in seen]
		for status in STATUSES:
			group = [p for p in postings if p.status == status]
			if not group:
				continue
			oldest = min(get_datetime(p.creation) for p in group)
			age = (now - oldest).total_seconds() / 60.0 if status not in ("Posted", "Cancelled") else None
			errors = [p.last_error for p in group if p.last_error]
			rows.append(
				{
					"adapter": adapter,
					"outbox": doctype,
					"status": status,
					"count": len(group),
					"oldest_minutes": age,
					"max_attempts": max(p.attempts or 0 for p in group),
					"next_attempt_at": min(
						(p.next_attempt_at for p in group if p.next_attempt_at), default=None
					),
					"last_error": (errors[-1] or "")[:140] if errors else None,
				}
			)
			if status == "Failed":
				failed_total += len(group)
			if status in ("Queued", "Sending", "Retry", "Unknown"):
				waiting_total += len(group)
				oldest_wait = max(oldest_wait, age or 0)
	return (
		get_columns(),
		rows,
		None,
		get_chart(rows),
		[
			summary_item(_("Failed"), failed_total, "Int", "Red" if failed_total else "Green"),
			summary_item(_("Waiting"), waiting_total, "Int", "Orange" if waiting_total else "Green"),
			summary_item(_("Oldest Waiting (min)"), oldest_wait, "Float"),
		],
	)


def get_columns():
	return [
		{"fieldname": "adapter", "label": _("Adapter"), "fieldtype": "Data", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "count", "label": _("Postings"), "fieldtype": "Int", "width": 90},
		{"fieldname": "oldest_minutes", "label": _("Oldest (min)"), "fieldtype": "Float", "width": 100},
		{"fieldname": "max_attempts", "label": _("Max Attempts"), "fieldtype": "Int", "width": 100},
		{"fieldname": "next_attempt_at", "label": _("Next Attempt"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "last_error", "label": _("Last Error"), "fieldtype": "Data", "width": 320},
		{
			"fieldname": "outbox",
			"label": _("Outbox"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 130,
		},
	]


def get_chart(rows):
	adapters = sorted({r["adapter"] for r in rows})
	shown = ("Queued", "Retry", "Unknown", "Failed", "Posted")
	by = {(r["adapter"], r["status"]): r["count"] for r in rows}
	return chart_of(
		adapters,
		[{"name": _(status), "values": [by.get((a, status), 0) for a in adapters]} for status in shown],
		"bar",
		colors=["#2490ef", "#ffa00a", "#b8c2cc", "#ff5858", "#29cd42"],
		barOptions={"stacked": 1},
	)
