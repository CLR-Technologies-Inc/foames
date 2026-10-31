# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Performs one ERPNext outbox posting.

Each operation calls the function ERPNext's own forms call, looked up by dotted path at run time
(`frappe.get_attr`), so nothing is imported from ERPNext at module load and the core still installs
without it. The ERPNext functions validate the posting the way the Work Order or Job Card form
would: stock, quantities, statuses and permissions.

A posting runs as the user who queued it, so ERPNext's permission checks apply to that user.
"""

from dataclasses import dataclass, field

import frappe
from frappe import _
from frappe.utils import cint, flt

from foames.foames_adapters.erpnext.postings import Operation

WORK_ORDER_API = "erpnext.manufacturing.doctype.work_order.work_order"
JOB_CARD_API = "erpnext.manufacturing.doctype.job_card.job_card"


@dataclass
class Result:
	"""What a posting produced: the ERPNext document and a response for the outbox record."""

	doctype: str
	name: str
	response: dict = field(default_factory=dict)
	# True when the document existed before this attempt (found by marker or already in the state asked for).
	existing: bool = False


def execute(operation: Operation, payload: dict, marker: str) -> Result:
	"""Perform the posting, or find the document an earlier attempt already created."""
	existing = find_existing(operation, payload, marker)
	if existing:
		return existing
	if operation.doctype == "Stock Entry":
		return post_stock_entry(operation.label, payload, marker)
	if operation.label == "Job Card Time Log":
		return post_job_card_time_log(payload, marker)
	if operation.label == "Work Order Status":
		return set_work_order_status(payload)
	raise ValueError(f"No executor for {operation.label}")


def find_existing(operation: Operation, payload: dict, marker: str) -> Result | None:
	"""A document a previous attempt created for this posting, found by its marker."""
	if operation.doctype == "Stock Entry":
		name = frappe.db.get_value(
			"Stock Entry", {"remarks": ("like", f"{marker}%"), "docstatus": ("<", 2)}, "name"
		)
		if name:
			return Result("Stock Entry", name, {"found_by": "marker"}, existing=True)
	elif operation.label == "Job Card Time Log":
		remarks = frappe.db.get_value("Job Card", payload["job_card"], "remarks") or ""
		if marker in remarks:
			return Result("Job Card", payload["job_card"], {"found_by": "marker"}, existing=True)
	return None


def post_stock_entry(purpose: str, payload: dict, marker: str) -> Result:
	"""Build the Stock Entry the Work Order form would build for this purpose, then insert and
	(by default) submit it."""
	make_stock_entry = frappe.get_attr(f"{WORK_ORDER_API}.make_stock_entry")
	qty = payload.get("qty")
	values = make_stock_entry(payload["work_order"], purpose, qty=flt(qty) if qty is not None else None)
	doc = frappe.get_doc(values)
	doc.remarks = f"{marker} {payload.get('remarks') or ''}".strip()
	if payload.get("posting_date"):
		doc.set_posting_time = 1
		doc.posting_date = payload["posting_date"]
		if payload.get("posting_time"):
			doc.posting_time = payload["posting_time"]
	doc.insert()
	if payload.get("submit", True):
		doc.submit()
	return Result(
		"Stock Entry",
		doc.name,
		{
			"purpose": doc.purpose,
			"docstatus": doc.docstatus,
			"fg_completed_qty": doc.fg_completed_qty,
			"items": [
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"s_warehouse": row.s_warehouse,
					"t_warehouse": row.t_warehouse,
				}
				for row in doc.items
			],
		},
	)


def post_job_card_time_log(payload: dict, marker: str) -> Result:
	"""Add a time log to a Job Card through ERPNext's own `make_time_log`, which validates the
	operation sequence and updates the Job Card's status and totals. With `submit` and a completion
	time, the Job Card is submitted once its completed quantity reaches the quantity it is for."""
	make_time_log = frappe.get_attr(f"{JOB_CARD_API}.make_time_log")
	name = payload["job_card"]
	args = {"job_card_id": name}
	for key in ("start_time", "complete_time", "completed_qty", "employees"):
		if payload.get(key) not in (None, ""):
			args[key] = payload[key]
	make_time_log(args)

	remarks = frappe.db.get_value("Job Card", name, "remarks") or ""
	frappe.db.set_value("Job Card", name, "remarks", f"{remarks}\n{marker}".strip(), update_modified=False)

	doc = frappe.get_doc("Job Card", name)
	submitted = False
	submit = (
		payload["submit"]
		if "submit" in payload
		else frappe.db.get_single_value("ERPNext Adapter Settings", "submit_job_cards_when_complete")
	)
	if submit and payload.get("complete_time") and doc.docstatus == 0:
		# make_time_log writes the rows directly; the total on the parent is only summed on save.
		completed = max(flt(doc.total_completed_qty), sum(flt(row.completed_qty) for row in doc.time_logs))
		if completed >= flt(doc.for_quantity):
			doc.submit()
			submitted = True
	return Result(
		"Job Card",
		name,
		{
			"status": doc.status,
			"docstatus": doc.docstatus,
			"total_completed_qty": doc.total_completed_qty,
			"total_time_in_mins": doc.total_time_in_mins,
			"submitted": submitted,
		},
	)


def set_work_order_status(payload: dict) -> Result:
	"""Stop, resume or close a Work Order. Already being in the asked-for state is a success."""
	name, status = payload["work_order"], payload["status"]
	current = frappe.db.get_value("Work Order", name, ["status", "docstatus"], as_dict=True)
	if not current:
		frappe.throw(_("Work Order {0} does not exist").format(name), frappe.DoesNotExistError)
	if cint(current.docstatus) != 1:
		frappe.throw(_("Work Order {0} is not submitted").format(name))
	already = (
		(status == "Stopped" and current.status == "Stopped")
		or (status == "Resumed" and current.status not in ("Stopped", "Closed"))
		or (status == "Closed" and current.status == "Closed")
	)
	if already:
		return Result("Work Order", name, {"status": current.status}, existing=True)
	if status == "Closed":
		frappe.get_attr(f"{WORK_ORDER_API}.close_work_order")(name, "Closed")
	else:
		frappe.get_attr(f"{WORK_ORDER_API}.stop_unstop")(name, status)
	return Result("Work Order", name, {"status": frappe.db.get_value("Work Order", name, "status")})
