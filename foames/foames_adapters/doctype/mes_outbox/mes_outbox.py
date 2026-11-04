# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime

from foames.foames_adapters.mes import outbox

PENDING = ("Queued", "Retry", "Unknown")
# A posting left in Sending this long belongs to a worker that died mid-send.
STALE_SENDING = timedelta(minutes=15)
BATCH_SIZE = 50
# Pages of due postings one run looks through before giving up on finding BATCH_SIZE sendable ones.
MAX_PAGES = 10


def profile_of(connection: str):
	from foames.foames_adapters.doctype.mes_connection.mes_connection import profiles

	known = profiles()
	if connection not in known:
		frappe.throw(_("{0} is not a registered MES adapter").format(frappe.bold(connection)))
	return known[connection]


class MESOutbox(Document):
	"""One write to an MES, sent by the scheduler and retried until it is posted, fails, or needs a
	person to check it."""

	def validate(self):
		profile = profile_of(self.connection)
		if self.operation not in profile.operation_names():
			frappe.throw(
				_("{0} is not an operation of {1}. Operations: {2}").format(
					frappe.bold(self.operation), profile.label, ", ".join(profile.operation_names())
				)
			)
		try:
			outbox.prepare(profile.operation(self.operation), self.get_payload(), self.idempotency_key)
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
		"""An earlier posting of the same connection and sequence group that has not been posted yet."""
		if not self.sequence_group:
			return None
		return frappe.db.get_value(
			"MES Outbox",
			{
				"connection": self.connection,
				"sequence_group": self.sequence_group,
				"creation": ("<", self.creation),
				"status": ("not in", ("Posted", "Cancelled")),
			},
			"name",
			order_by="creation asc",
		)

	def attempt(self, client):
		"""Send once and record the outcome. The caller has claimed the row (status Sending)."""
		operation = profile_of(self.connection).operation(self.operation)
		payload = outbox.prepare(operation, self.get_payload(), self.idempotency_key)
		self.sent_payload = json.dumps(payload, indent=1)
		self.attempts = (self.attempts or 0) + 1
		self.last_attempt_at = now_datetime()

		result = outbox.send(client, operation, payload, verify_first=self.verify_first)
		self.status = result.status
		self.last_error = result.error or None
		self.error_details = json.dumps(result.details, indent=1, default=str) if result.details else None
		self.needs_check = 0
		if result.status == "Posted":
			self.mes_document = result.document
			self.posted_on = now_datetime()
			self.next_attempt_at = None
			self.response = json.dumps(result.response, indent=1, default=str) if result.response else None
		elif result.halt:
			# A Manual operation after an unclear answer: nobody resends it until a person has looked.
			self.needs_check = 1
			self.next_attempt_at = None
		elif result.status in ("Retry", "Unknown"):
			if outbox.give_up(self.attempts):
				self.status = "Failed"
				self.last_error = _("Gave up after {0} attempts. Last error: {1}").format(
					self.attempts, result.error
				)
			else:
				self.next_attempt_at = add_to_date(now_datetime(), seconds=outbox.retry_delay(self.attempts))
		if self.status == "Failed":
			self.next_attempt_at = None
		self.flags.verify_first = None
		self.save(ignore_permissions=True)

	@property
	def verify_first(self) -> bool:
		return bool(self.flags.verify_first) or self.status == "Unknown"

	@frappe.whitelist()
	def requeue(self):
		"""Send a posting again after a person has fixed the cause, or checked the system for a posting
		that stopped as Unknown and found nothing."""
		frappe.only_for(("System Manager", "FoaMES Engineer"))
		if self.status not in ("Failed", "Unknown"):
			frappe.throw(_("Only failed postings, or postings that need a check, can be requeued"))
		# A posting that can be checked automatically is checked first; one that cannot is sent again,
		# because the person who requeues it has checked the system.
		operation = profile_of(self.connection).operation(self.operation)
		manual = outbox.effective(operation, self.get_payload()).idempotency == outbox.MANUAL
		self.status = "Queued" if manual else "Unknown"
		self.needs_check = 0
		self.attempts = 0
		self.next_attempt_at = None
		self.save()

	@frappe.whitelist()
	def mark_posted(self, document: str = ""):
		"""A person found the record the unclear send created: record it instead of sending again."""
		frappe.only_for(("System Manager", "FoaMES Engineer"))
		if self.status != "Unknown":
			frappe.throw(_("Only a posting that needs a check can be marked as posted"))
		self.status = "Posted"
		self.needs_check = 0
		self.mes_document = document or self.mes_document
		self.posted_on = now_datetime()
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
		self.needs_check = 0
		self.next_attempt_at = None
		self.save()


def enqueue(
	connection: str,
	operation: str,
	payload: dict,
	idempotency_key: str,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> str:
	"""Queue a write to an MES and return the outbox record's name.

	`connection` is the adapter key (the MES Connection's name). Queuing the same idempotency key
	twice returns the first record, so callers can retry freely. Use a key that names the business
	event, for example "<work order>:<operation>:complete".
	"""
	existing = frappe.db.get_value("MES Outbox", {"idempotency_key": idempotency_key}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "MES Outbox",
			"connection": connection,
			"operation": operation,
			"payload": json.dumps(payload, indent=1, default=str),
			"idempotency_key": idempotency_key,
			"sequence_group": sequence_group,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"status": "Queued",
		}
	)
	frappe.db.savepoint("foames_mes_enqueue")
	try:
		doc.insert(ignore_permissions=True)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point="foames_mes_enqueue")
		return frappe.db.get_value("MES Outbox", {"idempotency_key": idempotency_key}, "name")
	return doc.name


def release_stale_sending():
	"""A posting a dead worker left in Sending goes back to the queue as Unknown, to be checked first."""
	stale = frappe.get_all(
		"MES Outbox",
		filters={"status": "Sending", "last_attempt_at": ("<", now_datetime() - STALE_SENDING)},
		pluck="name",
	)
	for name in stale:
		frappe.db.set_value("MES Outbox", name, "status", "Unknown", update_modified=False)


def due_postings(connection: str, after=None, page_size: int = BATCH_SIZE * 4) -> list[dict]:
	"""Pending postings of one connection whose next attempt is due, oldest first, one page at a
	time. Postings that need a person's check are left alone."""
	filters = {"connection": connection, "status": ("in", PENDING), "needs_check": 0}
	if after:
		filters["creation"] = (">", after)
	return frappe.get_all(
		"MES Outbox",
		filters=filters,
		or_filters=[["next_attempt_at", "is", "not set"], ["next_attempt_at", "<=", now_datetime()]],
		fields=["name", "creation", "sequence_group"],
		order_by="creation asc",
		limit_page_length=page_size,
	)


def process_outbox(transport=None) -> int:
	"""Send due postings of every enabled connection in queue order. Runs from the scheduler.

	Commits after each posting, so the record of a write the system accepted is never rolled back by
	a later failure in the same run.
	"""
	from foames.foames_adapters.doctype.mes_connection.mes_connection import enabled_connections

	release_stale_sending()
	sent = 0
	for connection in enabled_connections():
		if not connection.base_url:
			continue
		sent += _process_connection(connection, connection.client(transport))
	return sent


def _process_connection(connection, client) -> int:
	sent = 0
	after = None
	held_groups: set[str] = set()
	for _page in range(MAX_PAGES):
		if sent >= BATCH_SIZE:
			break
		rows = due_postings(connection.name, after)
		if not rows:
			break
		after = rows[-1].creation
		for row in rows:
			if sent >= BATCH_SIZE:
				break
			if row.sequence_group and row.sequence_group in held_groups:
				continue
			sent += _process_row(row, client, held_groups)
	return sent


def _process_row(row, client, held_groups: set) -> int:
	"""Claim and send one due posting. Returns 1 when an attempt was made, else 0."""
	doc = claim(row.name)
	if not doc:
		if row.sequence_group:
			held_groups.add(row.sequence_group)
		return 0
	try:
		doc.attempt(client)
	except Exception:
		# A bug, not an answer from the system. Back off like a failed send, and check before resending.
		frappe.db.rollback()
		attempts = (frappe.db.get_value("MES Outbox", row.name, "attempts") or 0) + 1
		frappe.db.set_value(
			"MES Outbox",
			row.name,
			{
				"status": "Failed" if outbox.give_up(attempts) else "Unknown",
				"attempts": attempts,
				"next_attempt_at": add_to_date(now_datetime(), seconds=outbox.retry_delay(attempts)),
			},
			update_modified=False,
		)
		frappe.log_error(title=_("MES outbox: {0} raised an error").format(row.name))
	if doc.status != "Posted" and doc.sequence_group:
		held_groups.add(doc.sequence_group)
	frappe.db.commit()  # nosemgrep
	return 1


def claim(name: str):
	"""Lock the row and move it to Sending, so a second worker skips it. Returns the document, or
	None when the posting is no longer pending or waits on an earlier one in its group."""
	status = frappe.db.sql("select status from `tabMES Outbox` where name=%s for update", (name,))
	if not status or status[0][0] not in PENDING:
		frappe.db.commit()  # nosemgrep
		return None
	doc = frappe.get_doc("MES Outbox", name)
	if doc.needs_check or doc.blocking_posting():
		frappe.db.commit()  # nosemgrep
		return None
	doc.flags.verify_first = doc.status == "Unknown"
	frappe.db.set_value(
		"MES Outbox", name, {"status": "Sending", "last_attempt_at": now_datetime()}, update_modified=False
	)
	frappe.db.commit()  # nosemgrep
	doc.status = "Sending"
	return doc
