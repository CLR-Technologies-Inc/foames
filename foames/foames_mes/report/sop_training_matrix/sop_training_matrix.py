# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Who is trained on which Effective SOP: one row per SOP revision and person who must acknowledge it.

A person must acknowledge an SOP when it requires acknowledgement and they hold one of its training
roles. Their status is Current when they acknowledged this revision, Outdated when only an earlier
revision of the same code, and Missing when none. Rows past the SOP's acknowledgement period are
marked overdue.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure import (
	DOCTYPE,
	users_with_roles,
)
from foames.foames_mes.report.utils import chart_of, summary_item
from foames.foames_mes.sop import ACK_STATUSES, acknowledgement_status, training_due

RANK = {"Missing": 0, "Outdated": 1, "Current": 2}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = matrix_rows(filters, getdate(nowdate()))
	counts = {s: sum(1 for r in rows if r["status"] == s) for s in ACK_STATUSES}
	total = len(rows)
	return (
		get_columns(),
		rows,
		None,
		chart_of(
			[_(s) for s in ACK_STATUSES],
			[{"name": _("People"), "values": [counts[s] for s in ACK_STATUSES]}],
			chart_type="donut",
			colors=["#29CD42", "#ECAD4B", "#E24C4C"],
		)
		if rows
		else None,
		[
			summary_item(
				_("Trained"), (counts["Current"] / total * 100.0) if total else 100.0, "Percent", "Green"
			),
			summary_item(_("Outdated"), counts["Outdated"], "Int", "Orange"),
			summary_item(_("Missing"), counts["Missing"], "Int", "Red"),
			summary_item(_("Overdue"), sum(1 for r in rows if r["overdue"]), "Int", "Red"),
		],
	)


def matrix_rows(filters, today) -> list[dict]:
	conditions = {"status": "Effective", "requires_acknowledgement": 1}
	if filters.get("sop_code"):
		conditions["sop_code"] = filters.sop_code.strip().upper()
	if filters.get("category"):
		conditions["category"] = filters.category
	rows = []
	for name in frappe.get_list(DOCTYPE, filters=conditions, pluck="name", order_by="sop_code"):
		doc = frappe.get_doc(DOCTYPE, name)
		users = users_with_roles([r.role for r in doc.training_roles])
		if filters.get("user"):
			users &= {filters.user}
		if not users:
			continue
		acks = {}
		for ack in frappe.get_all(
			"SOP Acknowledgement",
			filters={"sop_code": doc.sop_code, "user": ("in", list(users))},
			fields=["user", "revision", "acknowledged_on", "method"],
			order_by="revision asc",
		):
			acks[ack.user] = ack
		due = training_due(doc.effective_on, doc.acknowledge_within_days, today)
		due_by = (
			add_days(doc.effective_on, int(doc.acknowledge_within_days or 0)) if doc.effective_on else None
		)
		full_names = dict(
			frappe.get_all(
				"User", filters={"name": ("in", list(users))}, fields=["name", "full_name"], as_list=True
			)
		)
		for user in sorted(users):
			ack = acks.get(user)
			status = acknowledgement_status(ack.revision if ack else None, doc.revision)
			if filters.get("status") and status != filters.status:
				continue
			rows.append(
				{
					"sop": doc.name,
					"sop_code": doc.sop_code,
					"revision": doc.revision,
					"title": doc.title,
					"user": user,
					"full_name": full_names.get(user),
					"status": status,
					"acknowledged_revision": ack.revision if ack else None,
					"acknowledged_on": ack.acknowledged_on if ack else None,
					"method": ack.method if ack else None,
					"due_by": due_by,
					"overdue": 1 if (due and status != "Current") else 0,
				}
			)
	rows.sort(key=lambda r: (RANK[r["status"]], -r["overdue"], r["sop_code"], r["user"]))
	return rows


def get_columns():
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "user", "label": _("User"), "fieldtype": "Link", "options": "User", "width": 180},
		{"fieldname": "full_name", "label": _("Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "sop", "label": _("SOP"), "fieldtype": "Link", "options": DOCTYPE, "width": 150},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 200},
		{"fieldname": "revision", "label": _("Revision"), "fieldtype": "Int", "width": 80},
		{
			"fieldname": "acknowledged_revision",
			"label": _("Acknowledged Rev."),
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"fieldname": "acknowledged_on",
			"label": _("Acknowledged On"),
			"fieldtype": "Datetime",
			"width": 150,
		},
		{"fieldname": "method", "label": _("Method"), "fieldtype": "Data", "width": 140},
		{"fieldname": "due_by", "label": _("Due By"), "fieldtype": "Date", "width": 100},
		{"fieldname": "overdue", "label": _("Overdue"), "fieldtype": "Check", "width": 80},
	]
