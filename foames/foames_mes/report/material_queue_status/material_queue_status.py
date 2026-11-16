# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Open material queue entries with their readiness computed now: what is conditioning, ready, close
to or past its queue-time limit, expired or on hold, with minutes waited and minutes to the limit.
Entries are listed queue by queue in the order each queue's dispatch rule would start them, followed
by the entries that may not start.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from foames.foames_mes import material as m
from foames.foames_mes.material_flow import ENTRY_FIELDS, OPEN

ATTENTION = ("Q-time Warning", "Q-time Exceeded", "Expired", "On Hold")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = queue_rows(filters, now_datetime())
	count = lambda states: sum(1 for r in rows if r["readiness"] in states)  # noqa: E731
	return (
		get_columns(),
		rows,
		None,
		None,
		[
			summary_item("Ready", count(("Ready", "Q-time Warning")), "Green"),
			summary_item("Q-time Warning", count(("Q-time Warning",)), "Orange"),
			summary_item("Past limit or expired", count(("Q-time Exceeded", "Expired")), "Red"),
			summary_item("Conditioning", count(("Conditioning",)), "Blue"),
		],
	)


def summary_item(label, value, indicator):
	return {"label": _(label), "value": value, "datatype": "Int", "indicator": indicator}


def queue_rows(filters, now) -> list[dict]:
	conditions = {"disabled": 0}
	if filters.get("machine"):
		conditions["machine"] = filters.machine
	if filters.get("queue"):
		conditions["name"] = filters.queue
	queues = frappe.get_list(
		"Material Queue",
		filters=conditions,
		fields=["name", "title", "discipline", "qtime_warn_percent"],
		order_by="name",
	)
	rows = []
	for q in queues:
		entries = frappe.get_list(
			"Material Queue Entry",
			filters={"queue": q.name, "status": ["in", OPEN]},
			fields=[*ENTRY_FIELDS, "machine"],
			order_by="arrived_at asc",
		)
		waiting = [e for e in entries if e.status == "Waiting"]
		ordered = m.dispatch_order(waiting, q.discipline or "FIFO", now, q.qtime_warn_percent)
		position = {e["name"]: i + 1 for i, e in enumerate(ordered)}
		for e in entries:
			r = m.readiness(e, now, q.qtime_warn_percent)
			if filters.get("attention_only") and r["state"] not in ATTENTION:
				continue
			rows.append(
				{
					"queue": q.name,
					"queue_title": q.title,
					"position": position.get(e.name),
					"entry": e.name,
					"item": e.item,
					"batch": e.batch,
					"quantity": e.quantity,
					"uom": e.uom,
					"job_reference": e.job_reference,
					"status": e.status,
					"readiness": r["state"],
					"waited_minutes": r["waited_minutes"],
					"minutes_to_limit": r["minutes_to_limit"],
					"expires_at": e.expires_at,
					"mpc_level": e.mpc_level,
				}
			)
	rows.sort(key=lambda r: (r["queue"], r["position"] is None, r["position"] or 0))
	return rows


def get_columns():
	return [
		{
			"label": _("Queue"),
			"fieldname": "queue",
			"fieldtype": "Link",
			"options": "Material Queue",
			"width": 100,
		},
		{"label": _("Queue Title"), "fieldname": "queue_title", "fieldtype": "Data", "width": 160},
		{"label": _("Next"), "fieldname": "position", "fieldtype": "Int", "width": 60},
		{
			"label": _("Entry"),
			"fieldname": "entry",
			"fieldtype": "Link",
			"options": "Material Queue Entry",
			"width": 150,
		},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Data", "width": 120},
		{"label": _("Lot"), "fieldname": "batch", "fieldtype": "Data", "width": 100},
		{"label": _("Quantity"), "fieldname": "quantity", "fieldtype": "Float", "width": 80},
		{"label": _("Unit"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
		{"label": _("Job"), "fieldname": "job_reference", "fieldtype": "Data", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("Readiness"), "fieldname": "readiness", "fieldtype": "Data", "width": 120},
		{"label": _("Waited (min)"), "fieldname": "waited_minutes", "fieldtype": "Float", "width": 100},
		{"label": _("To Limit (min)"), "fieldname": "minutes_to_limit", "fieldtype": "Float", "width": 100},
		{"label": _("Expires"), "fieldname": "expires_at", "fieldtype": "Datetime", "width": 150},
		{"label": _("MPC"), "fieldname": "mpc_level", "fieldtype": "Int", "width": 60},
	]
