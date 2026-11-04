# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json

import frappe

from foames.foames_adapters.doctype.mes_outbox.mes_outbox import enqueue, process_outbox
from foames.foames_adapters.mes import outbox
from foames.foames_adapters.mes.fake import FakeMES, mes_error, no_content, ok
from foames.tests_compat import IntegrationTestCase

CONNECTION = "TULIP"
UPSERT = {"method": "PUT", "path": "api/v3/machines/m1/attributes", "body": {"state": "RUNNING"}}
MANUAL = {"method": "POST", "path": "api/v3/tables/t1/records", "body": {"order": "1000123"}}
REFERENCED = {
	**MANUAL,
	"reference_field": "externalRef",
	"lookup_path": "api/v3/tables/t1/records",
	"lookup_query": "externalRef",
}


def connection(**values):
	if frappe.db.exists("MES Connection", CONNECTION):
		doc = frappe.get_doc("MES Connection", CONNECTION)
	else:
		doc = frappe.new_doc("MES Connection")
		doc.adapter = CONNECTION
	doc.update(
		{
			"enabled": 1,
			"base_url": "https://plant.tulip.example",
			"auth_method": "Basic",
			"username": "apikey.2_abc",
			"password": "secret",
			"outbox_paused": 0,
			**values,
		}
	)
	doc.save()
	return doc


class TestMESOutbox(IntegrationTestCase):
	def setUp(self):
		connection()
		frappe.db.delete("MES Outbox")
		self.addCleanup(self.clean_up)

	def clean_up(self):
		# The outbox commits after each posting, so a rollback alone does not undo a test.
		frappe.db.rollback()
		frappe.db.delete("MES Outbox")
		frappe.db.delete("MES Connection", {"name": CONNECTION})
		frappe.db.commit()  # nosemgrep

	def test_enqueue_is_idempotent_and_validated(self):
		first = enqueue(CONNECTION, "REST Request", UPSERT, "m1:state:1")
		self.assertEqual(enqueue(CONNECTION, "REST Request", UPSERT, "m1:state:1"), first)
		self.assertEqual(frappe.db.count("MES Outbox"), 1)
		with self.assertRaises(frappe.ValidationError):
			enqueue(CONNECTION, "REST Request", {"method": "GET", "path": "x"}, "not-a-write")
		with self.assertRaises(frappe.ValidationError):
			enqueue(CONNECTION, "Confirm Order", UPSERT, "no-such-operation")
		with self.assertRaises(frappe.ValidationError):
			enqueue("NOT_AN_MES", "REST Request", UPSERT, "no-such-connection")

	def test_upsert_is_posted_with_basic_auth(self):
		name = enqueue(CONNECTION, "REST Request", UPSERT, "m1:state:2")
		fake = FakeMES().on("PUT", "/api/v3/machines/m1/attributes", no_content())
		process_outbox(transport=fake)
		doc = frappe.get_doc("MES Outbox", name)
		self.assertEqual(
			(doc.status, doc.mes_document, doc.attempts), ("Posted", "api/v3/machines/m1/attributes", 1)
		)
		request = fake.requests[-1]
		self.assertEqual(request["body"], {"state": "RUNNING"})
		self.assertTrue(request["headers"]["Authorization"].startswith("Basic "))

	def test_manual_unclear_answer_waits_for_a_person(self):
		name = enqueue(CONNECTION, "REST Request", MANUAL, "t1:record:1")
		process_outbox(transport=FakeMES().on("POST", "/api/v3/tables", TimeoutError("t")))
		doc = frappe.get_doc("MES Outbox", name)
		self.assertEqual((doc.status, doc.needs_check), ("Unknown", 1))
		self.assertIsNone(doc.next_attempt_at)
		# Nothing resends it on its own.
		fake = FakeMES().on("POST", "/api/v3/tables", ok({"id": "r1"}, 201))
		process_outbox(transport=fake)
		self.assertEqual(fake.requests, [])
		# A person looked and found nothing: requeue sends it again.
		doc.reload()
		doc.requeue()
		self.assertEqual((doc.status, doc.needs_check), ("Queued", 0))
		process_outbox(transport=fake)
		doc.reload()
		self.assertEqual((doc.status, doc.mes_document), ("Posted", "r1"))

	def test_mark_posted_records_what_a_person_found(self):
		name = enqueue(CONNECTION, "REST Request", MANUAL, "t1:record:2")
		process_outbox(transport=FakeMES().on("POST", "/api/v3/tables", mes_error(503, "down")))
		doc = frappe.get_doc("MES Outbox", name)
		self.assertEqual(doc.needs_check, 1)
		doc.mark_posted("r9")
		self.assertEqual((doc.status, doc.mes_document, doc.needs_check), ("Posted", "r9", 0))

	def test_client_reference_is_verified_before_resending(self):
		name = enqueue(CONNECTION, "REST Request", REFERENCED, "t1:record:3")
		process_outbox(transport=FakeMES().on("POST", "/api/v3/tables", TimeoutError("t")))
		doc = frappe.get_doc("MES Outbox", name)
		self.assertEqual((doc.status, doc.needs_check), ("Unknown", 0))
		self.assertTrue(doc.next_attempt_at)
		self.assertEqual(json.loads(doc.sent_payload)["body"]["externalRef"], outbox.marker("t1:record:3"))

		frappe.db.set_value("MES Outbox", name, "next_attempt_at", None)
		existing = {"id": "r7", "externalRef": outbox.marker("t1:record:3")}
		fake = FakeMES().on("GET", "/api/v3/tables/t1/records", ok([existing]))
		process_outbox(transport=fake)
		doc.reload()
		self.assertEqual((doc.status, doc.mes_document), ("Posted", "r7"))
		self.assertFalse([r for r in fake.requests if r["method"] == "POST"])

	def test_rejection_fails_and_holds_its_group(self):
		first = enqueue(CONNECTION, "REST Request", MANUAL, "a", sequence_group="t1")
		second = enqueue(CONNECTION, "REST Request", MANUAL, "b", sequence_group="t1")
		fake = FakeMES().on("POST", "/api/v3/tables", mes_error(400, "bad record"))
		process_outbox(transport=fake)
		self.assertEqual(frappe.db.get_value("MES Outbox", first, "status"), "Failed")
		self.assertEqual(frappe.db.get_value("MES Outbox", second, "status"), "Queued")
		self.assertEqual(len(fake.requests), 1)
		frappe.get_doc("MES Outbox", first).cancel_posting()
		process_outbox(transport=FakeMES().on("POST", "/api/v3/tables", ok({"id": "r2"}, 201)))
		self.assertEqual(frappe.db.get_value("MES Outbox", second, "status"), "Posted")

	def test_paused_or_disabled_connection_sends_nothing(self):
		enqueue(CONNECTION, "REST Request", UPSERT, "paused")
		connection(outbox_paused=1)
		fake = FakeMES().on("PUT", "/api", no_content())
		process_outbox(transport=fake)
		self.assertEqual(fake.requests, [])
		connection(outbox_paused=0, enabled=0)
		process_outbox(transport=fake)
		self.assertEqual(fake.requests, [])
