# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime

from foames.foames_adapters.insights_hub import outbox

PENDING = ("Queued", "Retry", "Unknown")
# A posting left in Sending this long belongs to a worker that died mid-send.
STALE_SENDING = timedelta(minutes=15)
BATCH_SIZE = 50
# Pages of due postings one run looks through before giving up on finding BATCH_SIZE sendable ones.
MAX_PAGES = 10


class InsightsHubOutbox(Document):
	"""One write to Insights Hub, sent by the scheduler and retried until it is posted or fails."""

	def validate(self):
		if self.operation not in outbox.operation_names():
			frappe.throw(_("{0} is not an Insights Hub outbox operation").format(frappe.bold(self.operation)))
		try:
			outbox.prepare(outbox.operation(self.operation), self.get_payload(), self.idempotency_key)
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
			"Insights Hub Outbox",
			{
				"sequence_group": self.sequence_group,
				"creation": ("<", self.creation),
				"status": ("not in", ("Posted", "Cancelled")),
			},
			"name",
			order_by="creation asc",
		)

	def attempt(self, client):
		"""Send once and record the outcome. The caller has claimed the row (status Sending)."""
		operation = outbox.operation(self.operation)
		payload = outbox.prepare(operation, self.get_payload(), self.idempotency_key)
		self.sent_payload = json.dumps(payload, indent=1)
		self.attempts = (self.attempts or 0) + 1
		self.last_attempt_at = now_datetime()

		result = outbox.send(client, operation, payload, verify_first=self.verify_first)
		self.status = result.status
		self.last_error = result.error or None
		self.error_details = json.dumps(result.details, indent=1) if result.details else None
		if result.status == "Posted":
			self.hub_document = result.document
			self.posted_on = now_datetime()
			self.next_attempt_at = None
			self.response = json.dumps(result.response, indent=1, default=str) if result.response else None
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
		"""Send a failed posting again, after the cause has been fixed in Insights Hub or the payload."""
		frappe.only_for(("System Manager", "FoaMES Engineer"))
		if self.status != "Failed":
			frappe.throw(_("Only failed postings can be requeued"))
		# A failed event may have been created after all (for example after a timeout), so check first.
		self.status = "Unknown"
		self.attempts = 0
		self.next_attempt_at = None
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


def enqueue(
	operation: str,
	payload: dict,
	idempotency_key: str,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> str:
	"""Queue a write to Insights Hub and return the outbox record's name.

	Queuing the same idempotency key twice returns the first record, so callers can retry freely.
	Use a key that names the business event, for example "<machine>:timeseries:<window end>".
	"""
	existing = frappe.db.get_value("Insights Hub Outbox", {"idempotency_key": idempotency_key}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Insights Hub Outbox",
			"operation": operation,
			"payload": json.dumps(payload, indent=1, default=str),
			"idempotency_key": idempotency_key,
			"sequence_group": sequence_group,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"status": "Queued",
		}
	)
	frappe.db.savepoint("foames_insights_hub_enqueue")
	try:
		doc.insert(ignore_permissions=True)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point="foames_insights_hub_enqueue")
		return frappe.db.get_value("Insights Hub Outbox", {"idempotency_key": idempotency_key}, "name")
	return doc.name


def release_stale_sending():
	"""A posting a dead worker left in Sending goes back to the queue as Unknown, to be checked first."""
	stale = frappe.get_all(
		"Insights Hub Outbox",
		filters={"status": "Sending", "last_attempt_at": ("<", now_datetime() - STALE_SENDING)},
		pluck="name",
	)
	for name in stale:
		frappe.db.set_value("Insights Hub Outbox", name, "status", "Unknown", update_modified=False)


def due_postings(after=None, page_size: int = BATCH_SIZE * 4) -> list[dict]:
	"""Pending postings whose next attempt is due, oldest first, one page at a time (`after` is the
	creation time of the last row of the previous page). Rows that wait on an earlier posting of
	their sequence group are still listed and skipped by `claim`."""
	filters = {"status": ("in", PENDING)}
	if after:
		filters["creation"] = (">", after)
	return frappe.get_all(
		"Insights Hub Outbox",
		filters=filters,
		or_filters=[["next_attempt_at", "is", "not set"], ["next_attempt_at", "<=", now_datetime()]],
		fields=["name", "creation", "sequence_group"],
		order_by="creation asc",
		limit_page_length=page_size,
	)


def process_outbox(transport=None):
	"""Send due postings in queue order. Runs from the scheduler.

	Commits after each posting, so the record of a write Insights Hub accepted is never rolled back by
	a later failure in the same run.
	"""
	from foames.foames_adapters.doctype.insights_hub_settings.insights_hub_settings import get_settings

	settings = get_settings()
	if not settings.enabled or settings.outbox_paused or not settings.gateway_url:
		return 0
	client = settings.client(transport)
	release_stale_sending()
	sent = 0
	after = None
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
		# A bug, not an answer from Insights Hub. Back off like a failed send, and check before resending.
		frappe.db.rollback()
		attempts = (frappe.db.get_value("Insights Hub Outbox", row.name, "attempts") or 0) + 1
		frappe.db.set_value(
			"Insights Hub Outbox",
			row.name,
			{
				"status": "Failed" if outbox.give_up(attempts) else "Unknown",
				"attempts": attempts,
				"next_attempt_at": add_to_date(now_datetime(), seconds=outbox.retry_delay(attempts)),
			},
			update_modified=False,
		)
		frappe.log_error(title=_("Insights Hub outbox: {0} raised an error").format(row.name))
	if doc.status != "Posted" and doc.sequence_group:
		held_groups.add(doc.sequence_group)
	frappe.db.commit()  # nosemgrep
	return 1


def claim(name: str):
	"""Lock the row and move it to Sending, so a second worker skips it. Returns the document, or
	None when the posting is no longer pending or waits on an earlier one in its group."""
	status = frappe.db.sql("select status from `tabInsights Hub Outbox` where name=%s for update", (name,))
	if not status or status[0][0] not in PENDING:
		frappe.db.commit()  # nosemgrep
		return None
	doc = frappe.get_doc("Insights Hub Outbox", name)
	if doc.blocking_posting():
		frappe.db.commit()  # nosemgrep
		return None
	doc.flags.verify_first = doc.status == "Unknown"
	frappe.db.set_value(
		"Insights Hub Outbox",
		name,
		{"status": "Sending", "last_attempt_at": now_datetime()},
		update_modified=False,
	)
	frappe.db.commit()  # nosemgrep
	doc.status = "Sending"
	return doc
