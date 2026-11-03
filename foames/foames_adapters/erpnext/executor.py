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
from frappe.utils import cint, flt, get_datetime

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
	if operation.label == "Job Card Production Log":
		return post_job_card_production_log(payload, marker)
	if operation.label == "Work Order Status":
		return set_work_order_status(payload)
	if operation.label == "Workstation Status":
		return set_workstation_status(payload)
	if operation.label == "Downtime Entry":
		return post_downtime_entry(payload, marker)
	raise ValueError(f"No executor for {operation.label}")


def find_existing(operation: Operation, payload: dict, marker: str) -> Result | None:
	"""A document a previous attempt created for this posting, found by its marker."""
	if operation.doctype == "Stock Entry":
		name = frappe.db.get_value(
			"Stock Entry", {"remarks": ("like", f"{marker}%"), "docstatus": ("<", 2)}, "name"
		)
		if name:
			return Result("Stock Entry", name, {"found_by": "marker"}, existing=True)
	elif operation.label in ("Job Card Time Log", "Job Card Production Log"):
		remarks = frappe.db.get_value("Job Card", payload["job_card"], "remarks") or ""
		if marker in remarks:
			return Result("Job Card", payload["job_card"], {"found_by": "marker"}, existing=True)
	elif operation.label == "Downtime Entry":
		name = frappe.db.get_value("Downtime Entry", {"remarks": ("like", f"%{marker}%")}, "name")
		if name:
			return Result("Downtime Entry", name, {"found_by": "marker"}, existing=True)
	return None


def post_stock_entry(purpose: str, payload: dict, marker: str) -> Result:
	"""Build the Stock Entry the Work Order form would build for this purpose, then insert and
	(by default) submit it."""
	make_stock_entry = frappe.get_attr(f"{WORK_ORDER_API}.make_stock_entry")
	qty = payload.get("qty")
	values = make_stock_entry(payload["work_order"], purpose, qty=flt(qty) if qty is not None else None)
	doc = frappe.get_doc(values)
	doc.remarks = f"{marker} {payload.get('remarks') or ''}".strip()
	if payload.get("posting_date") or payload.get("posting_time"):
		doc.set_posting_time = 1
		if payload.get("posting_date"):
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
	"""Add time to a Job Card through ERPNext's own `make_time_log`, which validates the operation
	sequence and updates the Job Card's status. `start_time` opens a time log row and `complete_time`
	closes the open one; a posting may carry both, which is applied as a start followed by a
	completion. A completion with no open row is rejected rather than silently dropped. With `submit`
	and a completion, the Job Card is submitted once its completed quantity reaches its for quantity.
	"""
	make_time_log = frappe.get_attr(f"{JOB_CARD_API}.make_time_log")
	name = payload["job_card"]
	start_time, complete_time = payload.get("start_time"), payload.get("complete_time")
	if complete_time and not start_time and not open_time_log(name):
		frappe.throw(
			_("Job Card {0} has no open time log to complete. Send start_time first, or both times.").format(
				name
			)
		)
	if start_time:
		args = {"job_card_id": name, "start_time": start_time}
		if payload.get("employees"):
			args["employees"] = payload["employees"]
		make_time_log(args)
	if complete_time:
		args = {"job_card_id": name, "complete_time": complete_time}
		if payload.get("completed_qty") is not None:
			args["completed_qty"] = payload["completed_qty"]
		make_time_log(args)

	remarks = frappe.db.get_value("Job Card", name, "remarks") or ""
	frappe.db.set_value("Job Card", name, "remarks", f"{remarks}\n{marker}".strip(), update_modified=False)

	doc = frappe.get_doc("Job Card", name)
	refresh_totals(doc)
	submitted = False
	submit = (
		payload["submit"]
		if "submit" in payload
		else frappe.db.get_single_value("ERPNext Adapter Settings", "submit_job_cards_when_complete")
	)
	if (
		submit
		and complete_time
		and doc.docstatus == 0
		and flt(doc.total_completed_qty) >= flt(doc.for_quantity)
	):
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


def open_time_log(job_card: str) -> str | None:
	"""The time log row of a Job Card that was started and not yet completed."""
	return frappe.db.get_value(
		"Job Card Time Log",
		{
			"parent": job_card,
			"parenttype": "Job Card",
			"from_time": ("is", "set"),
			"to_time": ("is", "not set"),
		},
		"name",
	)


def refresh_totals(doc):
	"""`make_time_log` writes the time log rows directly; the totals on the Job Card are only summed
	on save. Sum them here so the response, the floor and the submit check see the new row."""
	completed = sum(flt(row.completed_qty) for row in doc.time_logs)
	minutes = sum(flt(row.time_in_mins) for row in doc.time_logs)
	if (completed, minutes) != (flt(doc.total_completed_qty), flt(doc.total_time_in_mins)):
		doc.db_set(
			{"total_completed_qty": completed, "total_time_in_mins": minutes},
			update_modified=False,
		)


def post_job_card_production_log(payload: dict, marker: str) -> Result:
	"""Record a machine's production window on a Job Card: one time log per stretch the machine
	ran (or one for the whole window when it reported counts but no state), the good quantity as
	the last log's completed quantity, and the scrap added to the Job Card's process loss.

	The rows go through the Job Card's own validation (`validate_time_logs`), which rejects
	overlaps and sums the totals. A Job Card that is no longer a draft rejects the posting."""
	name = payload["job_card"]
	doc = frappe.get_doc("Job Card", name)
	if doc.docstatus != 0:
		frappe.throw(_("Job Card {0} is not a draft; its production cannot be logged").format(name))
	intervals = payload.get("run_intervals") or [[payload["from_time"], payload["to_time"]]]
	good = flt(payload.get("completed_qty"))
	for index, (from_time, to_time) in enumerate(intervals):
		row = {"from_time": get_datetime(from_time), "to_time": get_datetime(to_time), "completed_qty": 0}
		if index == len(intervals) - 1:
			row["completed_qty"] = good
		doc.append("time_logs", row)
	scrap = flt(payload.get("process_loss_qty"))
	loss_before = flt(doc.get("process_loss_qty"))
	if scrap and doc.meta.has_field("process_loss_qty"):
		doc.process_loss_qty = loss_before + scrap
	if doc.meta.has_field("pending_qty") and (loss_before + scrap or flt(doc.pending_qty)):
		# Recent ERPNext derives Process Loss Qty when it saves: for quantity less total completed
		# less pending. The pending quantity is what carries the loss, so it is set to leave exactly
		# the loss recorded so far (never more than what is left to make), and kept in step as
		# later windows complete more.
		total_completed = flt(doc.total_completed_qty) + good
		doc.pending_qty = max(flt(doc.for_quantity) - total_completed - loss_before - scrap, 0)
	note = payload.get("remarks") or ""
	if scrap:
		note = f"{note} (scrap {scrap:g})".strip()
	doc.remarks = "\n".join(
		part for part in ((doc.remarks or "").strip(), f"{marker} {note}".strip()) if part
	)
	doc.save()
	# Recent ERPNext versions derive Process Loss Qty themselves (planned minus completed) when the
	# Job Card is saved, so the scrap only counts as recorded when the value survived the save.
	loss_recorded = bool(scrap) and flt(doc.get("process_loss_qty")) == loss_before + scrap

	submitted = False
	submit = (
		payload["submit"]
		if "submit" in payload
		else frappe.db.get_single_value("ERPNext Adapter Settings", "submit_job_cards_when_complete")
	)
	if submit and flt(doc.total_completed_qty) + flt(doc.get("process_loss_qty")) >= flt(doc.for_quantity):
		doc.submit()
		submitted = True
	return Result(
		"Job Card",
		name,
		{
			"status": doc.status,
			"docstatus": doc.docstatus,
			"time_logs_added": len(intervals),
			"completed_qty": good,
			"process_loss_qty": scrap,
			"process_loss_recorded": loss_recorded,
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


def set_workstation_status(payload: dict) -> Result:
	"""Show a machine's state on its ERPNext Workstation (the status the Plant Floor page shows).
	Already showing it counts as done; a disabled Workstation stays Off, as ERPNext keeps it."""
	name = payload["workstation"]
	status = payload["status"]
	current = frappe.db.get_value("Workstation", name, ["status", "disabled"], as_dict=True)
	if not current:
		frappe.throw(_("Workstation {0} does not exist").format(name), frappe.DoesNotExistError)
	if cint(current.disabled):
		return Result("Workstation", name, {"status": current.status, "disabled": True}, existing=True)
	if current.status == status:
		return Result("Workstation", name, {"status": status}, existing=True)
	frappe.db.set_value("Workstation", name, "status", status)
	return Result("Workstation", name, {"status": status, "previous_status": current.status})


def post_downtime_entry(payload: dict, marker: str) -> Result:
	"""Create the ERPNext Downtime Entry for a stretch of downtime on a Workstation, or bring the
	one an earlier posting created for the same FoaMES Downtime Record up to date (its reason or
	notes may have been filled in after it closed). ERPNext requires an operator and validates
	that entries on a Workstation do not overlap."""
	from foames.foames_adapters.erpnext.postings import downtime_marker, stop_reason_for

	operator = payload.get("operator")
	if not operator:
		frappe.throw(
			_(
				"Downtime Entry needs an operator: ERPNext requires one on every entry. Set Downtime "
				"Operator in ERPNext Adapter Settings or pass operator in the payload."
			)
		)
	options = tuple(
		o for o in (frappe.get_meta("Downtime Entry").get_options("stop_reason") or "").split("\n") if o
	)
	stop_reason = payload.get("stop_reason")
	if stop_reason not in options:
		stop_reason = stop_reason_for(stop_reason, None, options)
	markers = [marker]
	record = payload.get("downtime_record")
	existing = None
	if record:
		stable = downtime_marker(record)
		markers.insert(0, stable)
		existing = frappe.db.get_value("Downtime Entry", {"remarks": ("like", f"%{stable}%")}, "name")
	remarks = " ".join([*markers, (payload.get("remarks") or "").strip()]).strip()
	values = {
		"workstation": payload["workstation"],
		"from_time": get_datetime(payload["from_time"]),
		"to_time": get_datetime(payload["to_time"]),
		"operator": operator,
		"stop_reason": stop_reason,
		"remarks": remarks,
	}
	if existing:
		doc = frappe.get_doc("Downtime Entry", existing)
		doc.update(values)
		doc.save()
		return Result("Downtime Entry", doc.name, {"downtime": doc.downtime, "updated": True})
	doc = frappe.get_doc({"doctype": "Downtime Entry", **values}).insert()
	return Result("Downtime Entry", doc.name, {"downtime": doc.downtime, "stop_reason": stop_reason})
