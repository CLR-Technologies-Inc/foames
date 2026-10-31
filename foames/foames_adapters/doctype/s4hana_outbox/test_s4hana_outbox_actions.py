# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The outbox with the function-import operations (cancellation, reversal) and the whitelisted
posting endpoints. Needs a Frappe site; S/4HANA is a scripted fake."""

import frappe

from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue, process_outbox
from foames.foames_adapters.doctype.s4hana_outbox.test_s4hana_outbox import enable_s4hana
from foames.foames_adapters.s4hana import api, outbox
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.tests_compat import IntegrationTestCase


class TestS4HANAOutboxActions(IntegrationTestCase):
	def setUp(self):
		enable_s4hana()
		frappe.db.delete("S4HANA Outbox")
		self.addCleanup(self.clean_up)

	def clean_up(self):
		frappe.db.rollback()
		frappe.db.delete("S4HANA Outbox")
		settings = frappe.get_single("S4HANA Settings")
		settings.enabled = 0
		settings.outbox_paused = 0
		settings.save()
		frappe.db.commit()  # nosemgrep

	def test_cancellation_is_validated_and_posted(self):
		with self.assertRaises(frappe.ValidationError):
			enqueue("Confirmation Cancellation", {"ConfirmationGroup": "77"}, "cancel-77")
		name = enqueue(
			"Confirmation Cancellation",
			{"ConfirmationGroup": "77", "ConfirmationCount": "1", "PostingDate": "2026-10-31"},
			"cancel-77-1",
		)
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf())
			.on("POST", "CancelProdnOrdConf", ok({"ConfirmationGroup": "77", "ConfirmationCount": "2"}))
		)
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertEqual((doc.status, doc.sap_document), ("Posted", "77|2"))
		post = next(r for r in fake.requests if r["method"] == "POST")
		self.assertEqual(post["query"]["ConfirmationCount"], "'1'")
		self.assertEqual(post["query"]["PostingDate"], "datetime'2026-10-31T00:00'")

	def test_reversal_records_a_stock_movement_reference(self):
		name = enqueue(
			"Material Document Reversal",
			{"MaterialDocumentYear": "2026", "MaterialDocument": "4900001234"},
			"rev-1",
		)
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "/Cancel", ok({"MaterialDocumentYear": "2026", "MaterialDocument": "4900001300"}))
		)
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertEqual((doc.status, doc.sap_document), ("Posted", "2026|4900001300"))
		self.assertTrue(doc.external_reference)
		reference = frappe.get_doc("External Reference", doc.external_reference)
		self.assertEqual(
			(reference.reference_type, reference.external_id), ("Stock Movement", "2026|4900001300")
		)

	def test_reversal_rejection_fails_without_retry(self):
		name = enqueue(
			"Material Document Reversal", {"MaterialDocumentYear": "2026", "MaterialDocument": "1"}, "rev-2"
		)
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "/Cancel", sap_error(400, "M7/021", "Deficit of stock"))
		)
		process_outbox(transport=fake)
		doc = frappe.get_doc("S4HANA Outbox", name)
		self.assertEqual(doc.status, "Failed")
		self.assertIn("Deficit", doc.last_error)

	def test_api_confirm_order_queues_a_marked_confirmation(self):
		frappe.set_user("Administrator")
		result = api.confirm_order(
			"1000123",
			"0010",
			"run-9:0010",
			yield_quantity="10",
			unit="KG",
			final=1,
			activities='[{"position": 2, "quantity": "1.5", "unit": "H"}]',
			start="2026-10-31 06:00:00",
			end="2026-10-31 07:30:00",
		)
		doc = frappe.get_doc("S4HANA Outbox", result["outbox"])
		self.assertEqual(
			(doc.operation, doc.status, doc.sequence_group),
			("Production Order Confirmation", "Queued", "1000123"),
		)
		payload = doc.get_payload()
		self.assertEqual(payload["ConfirmationYieldQuantity"], "10")
		self.assertEqual(payload["OpConfirmedWorkQuantity2"], "1.5")
		self.assertEqual(payload["ConfirmedExecutionStartTime"], "PT06H00M00S")
		self.assertIs(payload["IsFinalConfirmation"], True)
		self.assertNotIn("ConfirmationText", payload)
		# Calling again with the same key returns the same record.
		again = api.confirm_order("1000123", "0010", "run-9:0010", yield_quantity="10", unit="KG")
		self.assertEqual(again["outbox"], result["outbox"])
		with self.assertRaises(frappe.ValidationError):
			api.confirm_order("1000123", "0010", "run-9:bad", yield_quantity="10")  # no unit

	def test_api_goods_receipt_and_issue(self):
		frappe.set_user("Administrator")
		receipt = api.post_goods_receipt("1000123", "FG-1", "1010", "95.5", "KG", "run-9:receipt", batch="L7")
		issue = api.post_goods_issue(
			"1000123",
			'[{"material": "RM-1", "plant": "1010", "quantity": 50, "unit": "KG", "batch": "B1"}]',
			"run-9:issue",
		)
		receipt_doc = frappe.get_doc("S4HANA Outbox", receipt["outbox"])
		issue_doc = frappe.get_doc("S4HANA Outbox", issue["outbox"])
		self.assertEqual(receipt_doc.get_payload()["GoodsMovementCode"], "02")
		self.assertEqual(issue_doc.get_payload()["to_MaterialDocumentItem"][0]["GoodsMovementType"], "261")
		self.assertEqual({receipt_doc.sequence_group, issue_doc.sequence_group}, {"1000123"})

	def test_api_lists_every_operation(self):
		listed = {row["operation"] for row in api.get_operations()}
		self.assertEqual(listed, set(outbox.operation_names()))

	def test_api_reads_need_a_role(self):
		user = "s4hana-reader@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "Reader"}).insert(
				ignore_permissions=True
			)
		frappe.set_user(user)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.PermissionError):
			api.get_production_order("1000123")
