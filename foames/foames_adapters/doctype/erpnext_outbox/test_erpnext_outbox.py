# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Outbox behaviour that holds on any Frappe site, with or without ERPNext: validation, idempotent
queuing, sequence groups, requeue and cancel. Postings that reach ERPNext are tested in
foames/foames_adapters/erpnext/test_erpnext_integration.py."""

import json

import frappe

from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import (
	enqueue,
	process_outbox,
	release_stale_sending,
)
from foames.foames_adapters.erpnext import erpnext_installed
from foames.foames_adapters.erpnext import postings as rules
from foames.tests_compat import IntegrationTestCase

MANUFACTURE = {"work_order": "MFG-WO-TEST-1", "qty": 5}


class TestERPNextOutbox(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("ERPNext Outbox")

	def test_enqueue_is_idempotent(self):
		first = enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture")
		self.assertEqual(enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture"), first)
		self.assertEqual(frappe.db.count("ERPNext Outbox"), 1)
		doc = frappe.get_doc("ERPNext Outbox", first)
		self.assertEqual(doc.status, "Queued")
		self.assertEqual(json.loads(doc.payload), MANUFACTURE)

	def test_enqueue_validates_payload(self):
		with self.assertRaises(frappe.ValidationError):
			enqueue("Manufacture", {"qty": 5}, "wo-1:no-order")
		with self.assertRaises(frappe.ValidationError):
			enqueue("Work Order Status", {"work_order": "MFG-WO-TEST-1", "status": "Done"}, "wo-1:done")
		with self.assertRaises(frappe.ValidationError):
			enqueue("Not An Operation", MANUFACTURE, "wo-1:nope")

	def test_sequence_group_blocks_later_postings(self):
		first = enqueue(
			"Material Transfer for Manufacture",
			{"work_order": "MFG-WO-TEST-1"},
			"wo-1:transfer",
			"MFG-WO-TEST-1",
		)
		second = enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture", "MFG-WO-TEST-1")
		self.assertIsNone(frappe.get_doc("ERPNext Outbox", first).blocking_posting())
		self.assertEqual(frappe.get_doc("ERPNext Outbox", second).blocking_posting(), first)
		frappe.get_doc("ERPNext Outbox", first).cancel_posting()
		self.assertIsNone(frappe.get_doc("ERPNext Outbox", second).blocking_posting())

	def test_requeue_only_failed(self):
		name = enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture")
		doc = frappe.get_doc("ERPNext Outbox", name)
		with self.assertRaises(frappe.ValidationError):
			doc.requeue()
		frappe.db.set_value("ERPNext Outbox", name, {"status": "Failed", "attempts": 3, "last_error": "x"})
		doc = frappe.get_doc("ERPNext Outbox", name)
		doc.requeue()
		self.assertEqual(doc.status, "Queued")
		self.assertEqual(doc.attempts, 0)
		self.assertIsNone(doc.last_error)

	def test_posted_cannot_be_cancelled(self):
		name = enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture")
		frappe.db.set_value("ERPNext Outbox", name, "status", "Posted")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("ERPNext Outbox", name).cancel_posting()

	def test_record_error_classifies_and_backs_off(self):
		name = enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture")
		doc = frappe.get_doc("ERPNext Outbox", name)
		doc.record_error(frappe.QueryDeadlockError("deadlock"))
		row = frappe.db.get_value(
			"ERPNext Outbox", name, ["status", "attempts", "next_attempt_at"], as_dict=True
		)
		self.assertEqual(row.status, "Retry")
		self.assertEqual(row.attempts, 1)
		self.assertIsNotNone(row.next_attempt_at)
		doc.record_error(frappe.ValidationError("Stock is short"))
		row = frappe.db.get_value("ERPNext Outbox", name, ["status", "attempts", "last_error"], as_dict=True)
		self.assertEqual(row.status, "Failed")
		self.assertEqual(row.attempts, 2)
		self.assertIn("Stock is short", row.last_error)

	def test_record_error_gives_up_after_the_cap(self):
		name = enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture")
		frappe.db.set_value("ERPNext Outbox", name, "attempts", rules.MAX_ATTEMPTS - 1)
		frappe.get_doc("ERPNext Outbox", name).record_error(RuntimeError("flaky"))
		row = frappe.db.get_value("ERPNext Outbox", name, ["status", "last_error"], as_dict=True)
		self.assertEqual(row.status, "Failed")
		self.assertIn("Gave up", row.last_error)

	def test_stale_sending_is_released(self):
		name = enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture")
		frappe.db.set_value(
			"ERPNext Outbox",
			name,
			{
				"status": "Sending",
				"last_attempt_at": frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-1),
			},
		)
		release_stale_sending()
		self.assertEqual(frappe.db.get_value("ERPNext Outbox", name, "status"), "Retry")

	def test_outbox_does_nothing_until_enabled(self):
		enqueue("Manufacture", MANUFACTURE, "wo-1:manufacture")
		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.enable_postings = 0
		settings.save()
		self.assertEqual(process_outbox(), 0)
		self.assertEqual(
			frappe.db.get_value("ERPNext Outbox", {"idempotency_key": "wo-1:manufacture"}, "status"), "Queued"
		)

	def test_postings_cannot_be_enabled_without_erpnext(self):
		if erpnext_installed():
			self.skipTest("ERPNext is installed on this site")
		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.enable_postings = 1
		with self.assertRaises(frappe.ValidationError):
			settings.save()
