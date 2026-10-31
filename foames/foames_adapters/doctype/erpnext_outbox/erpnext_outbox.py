# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime

from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed
from foames.foames_adapters.erpnext import postings as rules

PENDING = ("Queued", "Retry")
# A posting left in Sending this long belongs to a worker that died mid-send. Its transaction was
# rolled back with it, so the posting simply goes back to the queue.
STALE_SENDING = timedelta(minutes=15)
BATCH_SIZE = 50
# Pages of due postings one run looks through before giving up on finding BATCH_SIZE sendable ones
# (a backlog of blocked or failed groups would otherwise be scanned to the end on every run).
MAX_PAGES = 10


class ERPNextOutbox(Document):
	"""One posting to ERPNext, performed by the scheduler and retried until it is posted or fails."""

	def validate(self):
		if self.operation not in rules.OPERATIONS:
			frappe.throw(_("{0} is not an ERPNext outbox operation").format(frappe.bold(self.operation)))
		try:
			rules.prepare(rules.OPERATIONS[self.operation], self.get_payload())
		except ValueError as e:
			frappe.throw(str(e))

	def get_payload(self) -> dict:
		try:
			payload = json.loads(self.payload or "{}")
		except ValueError:
			frappe.throw(_("Payload is not valid JSON"))
		if not isinstance(payload, dict):
			frappe.throw(_("Payload must be a JSON object"))
		return payload

	def blocking_posting(self) -> str | None:
		"""An earlier posting of the same sequence group that has not been posted yet."""
		if not self.sequence_group:
			return None
		return frappe.db.get_value(
			"ERPNext Outbox",
			{
				"sequence_group": self.sequence_group,
				"creation": ("<", self.creation),
				"status": ("not in", ("Posted", "Cancelled")),
			},
			"name",
			order_by="creation asc",
		)

	def attempt(self):
		"""Perform the posting once and record the outcome, all in the caller's transaction.

		The caller has claimed the row (status Sending). On success the ERPNext document and this
		record's update are committed together by the caller. On an error the caller rolls both back
		and records the failure separately, so a rejected posting leaves nothing behind in ERPNext.
		"""
		from foames.foames_adapters.erpnext import executor

		operation = rules.OPERATIONS[self.operation]
		payload = rules.prepare(operation, self.get_payload())
		result = executor.execute(operation, payload, rules.marker(self.idempotency_key))
		self.status = "Posted"
		self.attempts = (self.attempts or 0) + 1
		self.last_attempt_at = now_datetime()
		self.posted_on = now_datetime()
		self.next_attempt_at = None
		self.last_error = None
		self.error_details = None
		self.erp_doctype = result.doctype
		self.erp_document = result.name
		self.response = json.dumps(result.response, indent=1, default=str) if result.response else None
		self.link_document(operation)
		self.save(ignore_permissions=True)

	def record_error(self, error: BaseException):
		"""Record a failed attempt after the caller rolled the transaction back."""
		attempts = (frappe.db.get_value("ERPNext Outbox", self.name, "attempts") or 0) + 1
		outcome = rules.classify(rules.error_types(error))
		message = _error_message(error)
		values = {
			"attempts": attempts,
			"last_attempt_at": now_datetime(),
			"last_error": message,
			"error_details": json.dumps(
				{"type": type(error).__name__, "classes": rules.error_types(error)[:4]}, indent=1
			),
		}
		if outcome == "Failed" or rules.give_up(attempts):
			values["status"] = "Failed"
			values["next_attempt_at"] = None
			if outcome != "Failed":
				values["last_error"] = _("Gave up after {0} attempts. Last error: {1}").format(
					attempts, message
				)
		else:
			values["status"] = "Retry"
			values["next_attempt_at"] = add_to_date(now_datetime(), seconds=rules.retry_delay(attempts))
		frappe.db.set_value("ERPNext Outbox", self.name, values, update_modified=False)

	def link_document(self, operation):
		if not operation.reference_type or not self.erp_document:
			return
		from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

		try:
			self.external_reference = get_reference(
				operation.reference_type, self.erp_document, ADAPTER_KEY, ignore_permissions=True
			)
		except Exception:
			# The posting stands even if the reference cannot be recorded now.
			frappe.log_error(title=_("ERPNext outbox: could not record External Reference"))

	@frappe.whitelist()
	def requeue(self):
		"""Send a failed posting again, after the cause has been fixed in ERPNext or the payload."""
		frappe.only_for(("System Manager", "FoaMES Engineer"))
		if self.status != "Failed":
			frappe.throw(_("Only failed postings can be requeued"))
		self.status = "Queued"
		self.attempts = 0
		self.next_attempt_at = None
		self.last_error = None
		self.save()

	@frappe.whitelist()
	def cancel_posting(self):
		"""Drop a posting that will not be sent, which unblocks the rest of its sequence group."""
		frappe.only_for(("System Manager", "FoaMES Engineer"))
		if self.status in ("Posted", "Sending"):
			frappe.throw(_("A {0} posting cannot be cancelled").format(self.status.lower()))
		self.status = "Cancelled"
		self.next_attempt_at = None
		self.save()


def _error_message(error: BaseException) -> str:
	message = getattr(error, "message", None) or str(error) or type(error).__name__
	return frappe.utils.strip_html(str(message))[:1000]


def enqueue(
	operation: str,
	payload: dict,
	idempotency_key: str,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> str:
	"""Queue a posting to ERPNext and return the outbox record's name.

	Queuing the same idempotency key twice returns the first record, so callers can retry freely.
	Use a key that names the business event, for example "<work order>:<operation>:complete".
	Postings that share a `sequence_group` (typically the Work Order) are performed in queue order.
	"""
	return enqueue_posting(
		operation, payload, idempotency_key, sequence_group, reference_doctype, reference_name
	)[0]


def enqueue_posting(
	operation: str,
	payload: dict,
	idempotency_key: str,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> tuple[str, bool]:
	"""Like `enqueue`, and also says whether this call created the record (False when the key was
	already queued, including by a concurrent caller)."""
	existing = frappe.db.get_value("ERPNext Outbox", {"idempotency_key": idempotency_key}, "name")
	if existing:
		return existing, False
	doc = frappe.get_doc(
		{
			"doctype": "ERPNext Outbox",
			"operation": operation,
			"payload": json.dumps(payload, indent=1, default=str),
			"idempotency_key": idempotency_key,
			"sequence_group": sequence_group,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"status": "Queued",
		}
	)
	frappe.db.savepoint("foames_erpnext_enqueue")
	try:
		doc.insert(ignore_permissions=True)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point="foames_erpnext_enqueue")
		return frappe.db.get_value("ERPNext Outbox", {"idempotency_key": idempotency_key}, "name"), False
	return doc.name, True


def release_stale_sending():
	stale = frappe.get_all(
		"ERPNext Outbox",
		filters={"status": "Sending", "last_attempt_at": ("<", now_datetime() - STALE_SENDING)},
		pluck="name",
	)
	for name in stale:
		frappe.db.set_value("ERPNext Outbox", name, "status", "Retry", update_modified=False)


def due_postings(after=None, page_size: int = BATCH_SIZE * 4) -> list[dict]:
	"""Pending postings whose next attempt is due, oldest first, one page at a time (`after` is the
	creation time of the last row of the previous page). Rows that wait on an earlier posting of
	their sequence group are still listed and skipped by `claim`."""
	filters = {"status": ("in", PENDING)}
	if after:
		filters["creation"] = (">", after)
	return frappe.get_all(
		"ERPNext Outbox",
		filters=filters,
		or_filters=[["next_attempt_at", "is", "not set"], ["next_attempt_at", "<=", now_datetime()]],
		fields=["name", "creation", "sequence_group"],
		order_by="creation asc",
		limit_page_length=page_size,
	)


def outbox_enabled() -> bool:
	if not erpnext_installed():
		return False
	settings = frappe.get_cached_doc("ERPNext Adapter Settings")
	return bool(settings.enable_postings and not settings.outbox_paused)


def process_outbox():
	"""Perform due postings in queue order. Runs from the scheduler every few minutes.

	Commits after each posting, so a posting ERPNext accepted is never rolled back by a later
	failure in the same run.
	"""
	if not outbox_enabled():
		return 0
	release_stale_sending()
	sent = 0
	after = None
	# Groups found blocked or failed in this run: their later postings cannot go yet either.
	held_groups: set[str] = set()
	for _page in range(MAX_PAGES):
		if sent >= BATCH_SIZE:
			break
		rows = due_postings(after)
		if not rows:
			break
		after = rows[-1].creation
		for row in rows:
			if sent >= BATCH_SIZE:
				break
			if row.sequence_group and row.sequence_group in held_groups:
				continue
			sent += _process_row(row, held_groups)
	return sent


def _process_row(row, held_groups: set | None = None) -> int:
	"""Claim and perform one due posting. Returns 1 when an attempt was made, else 0."""
	doc = claim(row.name)
	if not doc:
		if held_groups is not None and row.sequence_group:
			held_groups.add(row.sequence_group)
		return 0
	user = frappe.session.user
	try:
		# A posting is performed as the user who queued it, so ERPNext's own permission checks on
		# Stock Entry, Job Card and Work Order apply to that user rather than to the scheduler.
		frappe.set_user(doc.owner or "Administrator")  # nosemgrep
		doc.attempt()
		frappe.db.commit()  # nosemgrep
	except Exception as e:
		# Roll back whatever ERPNext wrote before it failed, then record the failure on its own.
		frappe.db.rollback()
		doc.record_error(e)
		frappe.db.commit()  # nosemgrep
		if held_groups is not None and doc.sequence_group:
			held_groups.add(doc.sequence_group)
		if rules.classify(rules.error_types(e)) != "Failed":
			frappe.log_error(title=_("ERPNext outbox: {0} will be retried").format(row.name))
	finally:
		frappe.set_user(user)  # nosemgrep
	return 1


def claim(name: str):
	"""Lock the row and move it to Sending, so a second worker skips it. Returns the document, or
	None when the posting is no longer pending or waits on an earlier one in its group."""
	status = frappe.db.sql("select status from `tabERPNext Outbox` where name=%s for update", (name,))
	if not status or status[0][0] not in PENDING:
		frappe.db.commit()  # nosemgrep
		return None
	doc = frappe.get_doc("ERPNext Outbox", name)
	if doc.blocking_posting():
		frappe.db.commit()  # nosemgrep
		return None
	frappe.db.set_value(
		"ERPNext Outbox",
		name,
		{"status": "Sending", "last_attempt_at": now_datetime()},
		update_modified=False,
	)
	frappe.db.commit()  # nosemgrep
	doc.status = "Sending"
	return doc
