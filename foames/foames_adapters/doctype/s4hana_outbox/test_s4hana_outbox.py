# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json

import frappe

from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue, process_outbox
from foames.foames_adapters.s4hana import outbox
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.tests_compat import IntegrationTestCase

CONFIRMATION = {"OrderID": "1000123", "OrderOperation": "0010", "ConfirmationYieldQuantity": "10"}


def enable_s4hana():
	settings = frappe.get_single("S4HANA Settings")
	settings.update(
		{
			"enabled": 1,
			"base_url": "https://s4.example.com:44300",
			"sap_client": "100",
			"auth_method": "Basic",
			"username": "FOAMES_COMM",
			"password": "secret",
			"outbox_paused": 0,
		}
	)
	settings.save()


def confirmation_posted(group="77"):
	return (
		FakeS4HANA()
		.on("FETCH", "CONFIRMATION", csrf())
		.on("POST", "ProdnOrdConf2", ok({"ConfirmationGroup": group, "ConfirmationCount": "1"}, 201))
	)


class TestS4HANAOutbox(IntegrationTestCase):
	def restore_resolution_flag(self):
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 0)
		frappe.db.commit()  # nosemgrep

	def setUp(self):
		enable_s4hana()
		frappe.db.delete("S4HANA Outbox")
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

	def test_enqueue_is_idempotent(self):
		first = enqueue("Production Order Confirmation", CONFIRMATION, "seg-1:mix")
		self.assertEqual(enqueue("Production Order Confirmation", CONFIRMATION, "seg-1:mix"), first)
		self.assertEqual(frappe.db.count("S4HANA Outbox"), 1)

	def test_enqueue_validates_payload(self):
		with self.assertRaises(frappe.ValidationError):
			enqueue("Production Order Confirmation", {"ConfirmationYieldQuantity": "1"}, "no-order")

	def test_posts_with_marker(self):
		name = enqueue("Production Order Confirmation", CONFIRMATION, "seg-1:mix")
		fake = confirmation_posted()
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertEqual((doc.status, doc.sap_document, doc.attempts), ("Posted", "77|1", 1))
		post = next(r for r in fake.requests if r["method"] == "POST")
		self.assertEqual(post["body"]["ConfirmationText"], outbox.marker("seg-1:mix"))

	def test_rejection_fails_and_holds_its_group(self):
		first = enqueue("Production Order Confirmation", CONFIRMATION, "a", sequence_group="1000123")
		second = enqueue("Production Order Confirmation", CONFIRMATION, "b", sequence_group="1000123")
		fake = (
			FakeS4HANA()
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", sap_error(400, "RU/100", "Order is locked"))
		)
		process_outbox(transport=fake)
		self.assertEqual(frappe.db.get_value("S4HANA Outbox", first, "status"), "Failed")
		self.assertEqual(frappe.db.get_value("S4HANA Outbox", second, "status"), "Queued")
		self.assertEqual(len([r for r in fake.requests if r["method"] == "POST"]), 1)

		# Cancelling the failed posting releases the next one.
		frappe.get_doc("S4HANA Outbox", first).cancel_posting()
		process_outbox(transport=confirmation_posted())
		self.assertEqual(frappe.db.get_value("S4HANA Outbox", second, "status"), "Posted")

	def test_timeout_is_verified_before_resending(self):
		name = enqueue("Production Order Confirmation", CONFIRMATION, "seg-2:mix")
		fake = FakeS4HANA().on("FETCH", "CONFIRMATION", csrf()).on("POST", "ProdnOrdConf2", TimeoutError("t"))
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertEqual(doc.status, "Unknown")
		self.assertTrue(doc.next_attempt_at)

		frappe.db.set_value("S4HANA Outbox", name, "next_attempt_at", None)
		existing = {"results": [{"ConfirmationGroup": "90", "ConfirmationCount": "2"}]}
		fake = FakeS4HANA().on("GET", "ProdnOrdConf2", ok(existing))
		process_outbox(transport=fake)
		doc.reload()
		self.assertEqual((doc.status, doc.sap_document), ("Posted", "90|2"))
		self.assertFalse([r for r in fake.requests if r["method"] == "POST"])

	def test_paused_outbox_sends_nothing(self):
		settings = frappe.get_single("S4HANA Settings")
		settings.outbox_paused = 1
		settings.save()
		enqueue("Production Order Confirmation", CONFIRMATION, "paused")
		fake = confirmation_posted()
		process_outbox(transport=fake)
		self.assertEqual(fake.requests, [])

	def test_goods_movement_records_external_reference(self):
		payload = {
			"GoodsMovementCode": "02",
			"PostingDate": "/Date(1793318400000)/",
			"to_MaterialDocumentItem": {
				"results": [{"Material": "FG-1", "Plant": "1010", "GoodsMovementType": "101"}]
			},
		}
		# The outbox commits, so the flag would outlive this test's rollback: put it back afterwards.
		self.addCleanup(self.restore_resolution_flag)
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		name = enqueue("Goods Movement", payload, "gr-1")
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on(
				"POST",
				"A_MaterialDocumentHeader",
				ok({"MaterialDocumentYear": "2026", "MaterialDocument": "4900000001"}, 201),
			)
		)
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertEqual(doc.sap_document, "2026|4900000001")
		reference = frappe.get_doc("External Reference", doc.external_reference)
		self.assertEqual((reference.erp_system, reference.reference_type), ("S4HANA", "Stock Movement"))
		self.assertEqual(json.loads(doc.sent_payload)["MaterialDocumentHeaderText"], outbox.marker("gr-1"))
