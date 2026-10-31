# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The outbox record's lifecycle: requeue and cancel rules, stale Sending rows, paging of due postings,
giving up, sequence groups and the reconciliation report."""

from datetime import timedelta

import frappe
from frappe.utils import add_to_date, now_datetime

from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import (
	STALE_SENDING,
	due_postings,
	enqueue,
	process_outbox,
	release_stale_sending,
)
from foames.foames_adapters.doctype.s4hana_outbox.test_s4hana_outbox import (
	CONFIRMATION,
	confirmation_posted,
	enable_s4hana,
)
from foames.foames_adapters.report.s4hana_outbox_reconciliation.s4hana_outbox_reconciliation import execute
from foames.foames_adapters.s4hana import outbox
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_user


def rejected():
	return (
		FakeS4HANA()
		.on("FETCH", "CONFIRMATION", csrf())
		.on("POST", "ProdnOrdConf2", sap_error(400, "RU/100", "Order is locked"))
	)


class OutboxLifecycleTestCase(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		enable_s4hana()
		frappe.db.delete("S4HANA Outbox")
		frappe.db.commit()  # nosemgrep
		self.addCleanup(self.clean_up)

	def clean_up(self):
		# The outbox commits after each posting, so a rollback alone does not undo a test.
		frappe.db.rollback()
		frappe.db.delete("S4HANA Outbox")
		settings = frappe.get_single("S4HANA Settings")
		settings.enabled = 0
		settings.outbox_paused = 0
		settings.save()
		frappe.db.commit()  # nosemgrep

	def queue(self, key, group=None):
		return enqueue("Production Order Confirmation", CONFIRMATION, key, sequence_group=group)

	def status(self, name):
		return frappe.db.get_value("S4HANA Outbox", name, "status")


class TestRequeueAndCancel(OutboxLifecycleTestCase):
	def test_only_failed_postings_can_be_requeued(self):
		name = self.queue("rq-1")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("S4HANA Outbox", name).requeue()
		process_outbox(transport=rejected())
		self.assertEqual(self.status(name), "Failed")
		doc = frappe.get_doc("S4HANA Outbox", name)
		doc.requeue()
		self.assertEqual((doc.status, doc.attempts, doc.next_attempt_at), ("Unknown", 0, None))
		# A requeued posting is checked for an earlier copy before it is sent again.
		fake = confirmation_posted().on("GET", "ProdnOrdConf2", ok({"results": []}))
		process_outbox(transport=fake)
		self.assertEqual(self.status(name), "Posted")
		self.assertEqual(fake.requests[0]["method"], "GET")
		self.assertIn("$filter", fake.requests[0]["query"])
		self.assertEqual(fake.requests[-1]["method"], "POST")

	def test_posted_postings_cannot_be_cancelled(self):
		name = self.queue("cx-1")
		process_outbox(transport=confirmation_posted())
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("S4HANA Outbox", name).cancel_posting()
		self.assertEqual(self.status(name), "Posted")

	def test_queued_and_failed_postings_can_be_cancelled(self):
		queued = self.queue("cx-2")
		doc = frappe.get_doc("S4HANA Outbox", queued)
		doc.cancel_posting()
		self.assertEqual((doc.status, doc.next_attempt_at), ("Cancelled", None))
		failed = self.queue("cx-3")
		process_outbox(transport=rejected())
		frappe.get_doc("S4HANA Outbox", failed).cancel_posting()
		self.assertEqual(self.status(failed), "Cancelled")
		# A cancelled posting is never sent.
		fake = confirmation_posted()
		process_outbox(transport=fake)
		self.assertEqual(fake.requests, [])

	def test_requeue_and_cancel_are_for_system_managers(self):
		name = self.queue("perm-1")
		make_user("foames-outbox-engineer@example.com", "FoaMES Engineer")
		with as_user("foames-outbox-engineer@example.com"):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("S4HANA Outbox", name).cancel_posting()
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("S4HANA Outbox", name).requeue()


class TestQueueMechanics(OutboxLifecycleTestCase):
	def test_unknown_operation_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			enqueue("Teleport", {}, "tp-1")

	def test_stale_sending_rows_go_back_as_unknown(self):
		stale = self.queue("st-1")
		fresh = self.queue("st-2")
		frappe.db.set_value(
			"S4HANA Outbox",
			stale,
			{"status": "Sending", "last_attempt_at": now_datetime() - STALE_SENDING - timedelta(minutes=1)},
		)
		frappe.db.set_value("S4HANA Outbox", fresh, {"status": "Sending", "last_attempt_at": now_datetime()})
		release_stale_sending()
		self.assertEqual((self.status(stale), self.status(fresh)), ("Unknown", "Sending"))

	def test_due_postings_exclude_future_attempts_and_page_by_creation(self):
		names = [self.queue(f"due-{n}") for n in range(3)]
		later = self.queue("due-later")
		frappe.db.set_value("S4HANA Outbox", later, "next_attempt_at", add_to_date(now_datetime(), hours=1))
		posted = self.queue("due-posted")
		frappe.db.set_value("S4HANA Outbox", posted, "status", "Posted")
		due = [row.name for row in due_postings()]
		self.assertEqual(due, names)
		first = due_postings(page_size=2)
		self.assertEqual([r.name for r in first], names[:2])
		second = due_postings(after=first[-1].creation, page_size=2)
		self.assertEqual([r.name for r in second], names[2:])

	def test_gives_up_after_the_last_allowed_attempt(self):
		name = self.queue("gu-1")
		frappe.db.set_value("S4HANA Outbox", name, "attempts", outbox.MAX_ATTEMPTS - 1)
		fake = FakeS4HANA().on("FETCH", "CONFIRMATION", csrf()).on("POST", "ProdnOrdConf2", TimeoutError("t"))
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertEqual(
			(doc.status, doc.attempts, doc.next_attempt_at), ("Failed", outbox.MAX_ATTEMPTS, None)
		)
		self.assertIn("Gave up", doc.last_error)

	def test_transient_error_schedules_a_retry_with_backoff(self):
		name = self.queue("rt-1")
		fake = (
			FakeS4HANA()
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", sap_error(503, "", "busy"))
		)
		before = now_datetime()
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertIn(doc.status, ("Retry", "Unknown"))
		self.assertGreaterEqual((doc.next_attempt_at - before).total_seconds(), outbox.retry_delay(1) - 5)
		# Not due yet, so another run sends nothing.
		fake = confirmation_posted()
		process_outbox(transport=fake)
		self.assertEqual(fake.requests, [])

	def test_sequence_group_blocks_later_postings(self):
		first = self.queue("sg-1", group="1000123")
		second = self.queue("sg-2", group="1000123")
		alone = self.queue("sg-3")
		self.assertIsNone(frappe.get_doc("S4HANA Outbox", first).blocking_posting())
		self.assertEqual(frappe.get_doc("S4HANA Outbox", second).blocking_posting(), first)
		self.assertIsNone(frappe.get_doc("S4HANA Outbox", alone).blocking_posting())
		frappe.db.set_value("S4HANA Outbox", first, "status", "Posted")
		self.assertIsNone(frappe.get_doc("S4HANA Outbox", second).blocking_posting())

	def test_postings_in_a_group_go_out_in_order(self):
		names = [self.queue(f"ord-{n}", group="1000124") for n in range(3)]
		fake = confirmation_posted()
		process_outbox(transport=fake)
		self.assertEqual([self.status(n) for n in names], ["Posted"] * 3)
		sent = [r["body"]["ConfirmationText"] for r in fake.requests if r["method"] == "POST"]
		self.assertEqual(sent, [outbox.marker(f"ord-{n}") for n in range(3)])


class TestReconciliationReport(OutboxLifecycleTestCase):
	def test_open_postings_with_what_holds_them(self):
		first = self.queue("rep-1", group="G1")
		second = self.queue("rep-2", group="G1")
		other = self.queue("rep-3", group="G2")
		posted = self.queue("rep-4")
		process_outbox(transport=rejected())  # the first of each group fails and holds the rest
		frappe.db.set_value("S4HANA Outbox", posted, "status", "Posted")
		columns, rows = execute()
		self.assertIn("held_by", [c["fieldname"] for c in columns])
		by_name = {row.name: row for row in rows}
		self.assertNotIn(posted, by_name)
		self.assertEqual(by_name[first].status, "Failed")
		self.assertIsNone(by_name[first].get("held_by"))
		self.assertEqual(by_name[second].get("held_by"), first)
		self.assertIsNone(by_name[other].get("held_by"))

	def test_filters(self):
		self.queue("rep-5", group="G5")
		posted = self.queue("rep-6", group="G6")
		frappe.db.set_value("S4HANA Outbox", posted, "status", "Posted")
		_, rows = execute({"include_posted": 1})
		self.assertIn(posted, [r.name for r in rows])
		_, rows = execute({"sequence_group": "G5"})
		self.assertEqual([r.sequence_group for r in rows], ["G5"])
