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

QUALITY_INSPECTION_API = "erpnext.stock.doctype.quality_inspection.quality_inspection"
WORK_ORDER_API = "erpnext.manufacturing.doctype.work_order.work_order"
JOB_CARD_API = "erpnext.manufacturing.doctype.job_card.job_card"


@dataclass
class Result:
	"""What a posting produced: the ERPNext document and a response for the outbox record."""

	doctype: str
	name: str | None  # None when the posting was performed but had nothing to create
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
	if operation.label == "Quality Inspection":
		return post_quality_inspection(payload, marker)
	raise ValueError(f"No executor for {operation.label}")


def find_existing(operation: Operation, payload: dict, marker: str) -> Result | None:
	"""A document a previous attempt created for this posting, found by its marker."""
	if operation.doctype == "Stock Entry":
		name = frappe.db.get_value(
			"Stock Entry", {"remarks": ("like", f"{marker}%"), "docstatus": ("<", 2)}, "name"
		)
		if name:
			# A replayed Manufacture posting still reports the finished good's identity, and an
			# entry whose first attempt lost the outbox update gets its references recorded now.
			doc = frappe.get_doc("Stock Entry", name)
			finished = finished_good_identity(doc)
			record_identity_references(finished, submitted=doc.docstatus == 1)
			return Result(
				"Stock Entry", name, {"found_by": "marker", "finished_good": finished}, existing=True
			)
	elif operation.label in ("Job Card Time Log", "Job Card Production Log"):
		remarks = frappe.db.get_value("Job Card", payload["job_card"], "remarks") or ""
		if marker in remarks:
			return Result("Job Card", payload["job_card"], {"found_by": "marker"}, existing=True)
	elif operation.label == "Downtime Entry":
		name = frappe.db.get_value("Downtime Entry", {"remarks": ("like", f"%{marker}%")}, "name")
		if name:
			return Result("Downtime Entry", name, {"found_by": "marker"}, existing=True)
	elif operation.label == "Quality Inspection":
		name = frappe.db.get_value(
			"Quality Inspection", {"remarks": ("like", f"{marker}%"), "docstatus": ("<", 2)}, "name"
		)
		if name:
			doc = frappe.get_doc("Quality Inspection", name)
			return Result(
				"Quality Inspection", name, {"found_by": "marker", **inspection_outcome(doc)}, existing=True
			)
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
	if purpose == "Manufacture" and (payload.get("batch_no") or payload.get("serial_nos")):
		name_finished_good(doc, payload.get("batch_no"), payload.get("serial_nos"))
	doc.insert()
	if payload.get("submit", True):
		doc.submit()
	finished = finished_good_identity(doc)
	record_identity_references(finished, submitted=doc.docstatus == 1)
	return Result(
		"Stock Entry",
		doc.name,
		{
			"purpose": doc.purpose,
			"docstatus": doc.docstatus,
			"fg_completed_qty": doc.fg_completed_qty,
			"finished_good": finished,
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


def finished_item_row(doc):
	return next((row for row in doc.items if cint(row.get("is_finished_item"))), None)


def name_finished_good(doc, batch_no: str | None, serial_nos: list[str] | None):
	"""Give the Manufacture entry's finished good the batch and serial numbers the floor knows it
	by, through ERPNext's own serial and batch fields (the bundle is built from them on save). A
	batch that does not exist yet is created for the item; serial numbers that do not exist yet
	are created by ERPNext when the entry is submitted."""
	row = finished_item_row(doc)
	if row is None:
		frappe.throw(_("The Manufacture entry for {0} has no finished item row").format(doc.work_order))
	if batch_no:
		if not frappe.db.exists("Batch", batch_no):
			frappe.get_doc({"doctype": "Batch", "batch_id": batch_no, "item": row.item_code}).insert()
		elif frappe.db.get_value("Batch", batch_no, "item") != row.item_code:
			frappe.throw(_("Batch {0} belongs to another item than {1}").format(batch_no, row.item_code))
		row.batch_no = batch_no
	if serial_nos:
		row.serial_no = "\n".join(serial_nos)
	row.use_serial_batch_fields = 1


def finished_good_identity(doc) -> dict | None:
	"""The finished good's item, batch and serial numbers as ERPNext recorded them (from the row's
	bundle once the entry is submitted, else from the fields), for traceability in FoaMES."""
	row = finished_item_row(doc)
	if row is None:
		return None
	batches: list[str] = []
	serials: list[str] = []
	bundle = (
		frappe.db.get_value("Stock Entry Detail", row.name, "serial_and_batch_bundle") if row.name else None
	)
	if bundle:
		batches = list(
			frappe.get_attr("erpnext.stock.serial_batch_bundle.get_batches_from_bundle")(bundle) or {}
		)
		serials = list(
			frappe.get_attr("erpnext.stock.serial_batch_bundle.get_serial_nos_from_bundle")(bundle) or []
		)
	if not batches and row.get("batch_no"):
		batches = [row.batch_no]
	if not serials and row.get("serial_no"):
		serials = [s.strip() for s in str(row.serial_no).replace(",", "\n").split("\n") if s.strip()]
	return {
		"item_code": row.item_code,
		"qty": row.qty,
		"warehouse": row.t_warehouse,
		"batch_no": batches[0] if len(batches) == 1 else None,
		"batch_nos": batches,
		"serial_nos": serials,
	}


def record_identity_references(finished: dict | None, submitted: bool = True):
	"""External References for the batch and serial numbers a Manufacture entry produced, so FoaMES
	records (quality, process events, agents) can point at them from now on. A Batch exists from
	the draft on; Serial No records are created by ERPNext on submit, so a draft entry's serial
	numbers are referenced once it is submitted (by a replay of the posting, or on the next entry
	that names them)."""
	if not finished:
		return
	from foames.foames_adapters.erpnext import ADAPTER_KEY
	from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

	for batch_no in finished.get("batch_nos") or []:
		get_reference("Batch", batch_no, ADAPTER_KEY, ignore_permissions=True)
	if not submitted:
		return
	for serial_no in finished.get("serial_nos") or []:
		get_reference("Serial Number", serial_no, ADAPTER_KEY, ignore_permissions=True)


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


def post_quality_inspection(payload: dict, marker: str) -> Result:
	"""Create an ERPNext Quality Inspection for a Job Card (in process) or a Stock Entry (the
	finished good coming in) from the readings the floor took, judged by ERPNext's own acceptance
	criteria: each reading takes its limits or formula from the Quality Inspection Template the Job
	Card's operation, the BOM or the item names, and ERPNext sets the reading's and the
	inspection's status on save. A reading for a parameter the template does not cover needs its
	own `min_value`/`max_value` or a `status`, so nothing is judged against limits that were never
	set. Submitting (the default) links the inspection to the Job Card or the Stock Entry row, which
	is what ERPNext checks when the Job Card is completed."""
	reference_type, reference_name = payload["reference_type"], payload["reference_name"]
	reference = frappe.get_doc(reference_type, reference_name)
	item_code, bom_no, template = inspection_subject(reference, payload.get("item_code"))
	template = payload.get("template") or template
	submit = payload.get("submit")
	if payload.get("measurements"):
		# Read the machine's measurements now, so a reading a gateway delivered after the posting
		# was queued still counts; the window is half-open, so a reading at the moment one job gave
		# way to the next belongs to the next job only.
		from foames.foames_adapters.erpnext.quality import measurement_readings

		window = payload["measurements"]
		readings = measurement_readings(
			window["machine"],
			window["since"],
			window["until"],
			window.get("specifications"),
			until_inclusive=False,
		)
		if not readings:
			return Result(
				"Quality Inspection",
				None,
				{
					"status": None,
					"readings": [],
					"message": _(
						"{0} measured nothing for the template's parameters between {1} and {2}"
					).format(window["machine"], window["since"], window["until"]),
				},
			)
		payload = {**payload, "readings": readings}
		if submit is None:
			# Submitting stands for "inspected": only when every parameter of the template was measured.
			measured = {r["specification"] for r in readings}
			submit = bool(template) and measured >= set(template_criteria(template))
	if not item_code:
		frappe.throw(_("{0} {1} has no item to inspect").format(_(reference_type), reference_name))
	if item_code not in inspectable_items(reference):
		frappe.throw(
			_("{0} {1} does not produce or move item {2}, so it cannot be inspected for it").format(
				_(reference_type), reference_name, item_code
			)
		)
	criteria = template_criteria(template)
	for reading in payload["readings"]:
		if not frappe.db.exists("Quality Inspection Parameter", reading["specification"]):
			frappe.throw(
				_(
					"There is no Quality Inspection Parameter {0}. Create it in ERPNext, or name an existing one."
				).format(reading["specification"])
			)
		if (
			reading["specification"] not in criteria
			and "status" not in reading
			and not ("min_value" in reading and "max_value" in reading)
		):
			frappe.throw(
				_(
					"Reading {0} is not in template {1}: give it min_value and max_value, or a status, so it is "
					"not judged against limits that were never set."
				).format(reading["specification"], template or _("(none)"))
			)

	doc = frappe.new_doc("Quality Inspection")
	doc.update(
		{
			"inspection_type": payload["inspection_type"],
			"reference_type": reference_type,
			"reference_name": reference_name,
			"item_code": item_code,
			"bom_no": bom_no,
			"quality_inspection_template": template,
			"sample_size": payload.get("sample_size")
			or max(len(r.get("values") or [1]) for r in payload["readings"]),
			"inspected_by": payload.get("inspected_by") or frappe.session.user,
			"batch_no": payload.get("batch_no"),
			"item_serial_no": payload.get("serial_no"),
			"remarks": f"{marker} {payload.get('remarks') or ''}".strip(),
		}
	)
	for reading in payload["readings"]:
		row = doc.append("readings", {"specification": reading["specification"]})
		if reading["specification"] in criteria:
			row.update(criteria[reading["specification"]])
		else:
			row.numeric = int("values" in reading)
		for bound in ("min_value", "max_value"):
			if bound in reading:
				row.set(bound, reading[bound])
		if "values" in reading:
			row.numeric = 1
			for index, value in enumerate(reading["values"], start=1):
				row.set(f"reading_{index}", plain_number(value))
		else:
			row.reading_value = reading["value"]
		if "status" in reading:
			row.manual_inspection = 1
			row.status = reading["status"]
	doc.insert()
	if submit is None or submit:
		doc.submit()
	return Result("Quality Inspection", doc.name, inspection_outcome(doc))


def plain_number(value: float) -> str:
	"""A reading as ERPNext reads it back: plain decimal digits, no exponent, no grouping and no
	trailing zeros (`10.1`, `250`, `0.005`), with the decimal separator of the posting user's
	number format where the installed ERPNext parses readings in that format (recent releases;
	older ones read a point)."""
	text = f"{float(value):.10f}".rstrip("0").rstrip(".") or "0"
	try:
		number_format = frappe.get_attr(f"{QUALITY_INSPECTION_API}.get_reading_number_format")()
		decimal_str, _comma = frappe.get_attr(f"{QUALITY_INSPECTION_API}.get_reading_separators")(
			number_format
		)
	except (AttributeError, ImportError):
		return text
	return text.replace(".", decimal_str) if decimal_str != "." else text


def inspectable_items(reference) -> set[str]:
	"""The items a Quality Inspection on this document may be about: a Job Card's production item,
	a Stock Entry's items."""
	if reference.doctype == "Job Card":
		return {reference.production_item} if reference.production_item else set()
	return {row.item_code for row in reference.items}


def inspection_subject(reference, item_code: str | None) -> tuple[str | None, str | None, str | None]:
	"""(item, BOM, template) for the document a Quality Inspection is about: a Job Card inspects
	its production item against its operation's template, a Stock Entry its finished item (or the
	one named) against the BOM's template, falling back to the item's own template."""
	if reference.doctype == "Job Card":
		item = item_code or reference.production_item
		bom = reference.get("bom_no")
		template = reference.get("quality_inspection_template")
	else:
		row = finished_item_row(reference) or (reference.items[0] if reference.items else None)
		item = item_code or (row.item_code if row else None)
		bom = reference.get("bom_no")
		template = None
	if not template and bom:
		template = frappe.db.get_value("BOM", bom, "quality_inspection_template")
	if not template and item:
		template = frappe.db.get_value("Item", item, "quality_inspection_template")
	return item, bom, template


def template_criteria(template: str | None) -> dict[str, dict]:
	"""The acceptance criteria of a Quality Inspection Template by parameter, as ERPNext's own
	reader returns them (numeric flag, limits, formula, expected value)."""
	if not template:
		return {}
	get_template_details = frappe.get_attr(
		"erpnext.stock.doctype.quality_inspection_template.quality_inspection_template.get_template_details"
	)
	return {row["specification"]: dict(row) for row in get_template_details(template)}


def inspection_outcome(doc) -> dict:
	return {
		"status": doc.status,
		"docstatus": doc.docstatus,
		"reference_type": doc.reference_type,
		"reference_name": doc.reference_name,
		"item_code": doc.item_code,
		"readings": [
			{
				"specification": row.specification,
				"status": row.status,
				"values": [
					row.get(f"reading_{i}") for i in range(1, 11) if row.get(f"reading_{i}") not in (None, "")
				],
				"value": row.reading_value,
			}
			for row in doc.readings
		],
	}
