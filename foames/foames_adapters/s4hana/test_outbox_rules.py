# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The outbox rules on their own: markers, prepared payloads, document ids, the verify-first search
and the outcome of every kind of answer. No Frappe site needed."""

import unittest

from foames.foames_adapters.base import REFERENCE_TYPES
from foames.foames_adapters.s4hana import outbox
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.foames_adapters.s4hana.odata import Connection, ODataClient, Response


def client(fake):
	return ODataClient(Connection(base_url="https://s4", client="100"), transport=fake)


class TestOperations(unittest.TestCase):
	def test_every_operation_is_consistent(self):
		for key, operation in outbox.OPERATIONS.items():
			self.assertEqual(key, operation.label)
			self.assertTrue(operation.service and operation.entity_set and operation.marker_field)
			self.assertTrue(operation.document_fields)
			self.assertGreaterEqual(operation.marker_length, 20)
			if operation.reference_type:
				self.assertIn(operation.reference_type, REFERENCE_TYPES)

	def test_marker_shape(self):
		mark = outbox.marker("any key")
		self.assertTrue(mark.startswith(outbox.MARKER_PREFIX))
		self.assertEqual(len(mark), 23)
		self.assertEqual(mark, mark.upper())
		int(mark[len(outbox.MARKER_PREFIX) :], 16)

	def test_marker_fits_every_operation_untruncated(self):
		for operation in outbox.OPERATIONS.values():
			prepared = outbox.prepare(operation, {name: "x" for name in operation.lookup_fields}, "k")
			self.assertEqual(prepared[operation.marker_field], outbox.marker("k"))


class TestPrepare(unittest.TestCase):
	operation = outbox.OPERATIONS["Goods Movement"]

	def test_returns_a_copy(self):
		payload = {"GoodsMovementCode": "02"}
		prepared = outbox.prepare(self.operation, payload, "k")
		self.assertNotIn("MaterialDocumentHeaderText", payload)
		self.assertEqual(prepared["GoodsMovementCode"], "02")

	def test_overwrites_a_caller_supplied_text(self):
		prepared = outbox.prepare(self.operation, {"MaterialDocumentHeaderText": "mine"}, "k")
		self.assertEqual(prepared["MaterialDocumentHeaderText"], outbox.marker("k"))

	def test_empty_lookup_values_count_as_missing(self):
		confirmation = outbox.OPERATIONS["Process Order Confirmation"]
		with self.assertRaises(ValueError) as raised:
			outbox.prepare(confirmation, {"OrderID": ""}, "k")
		self.assertIn("OrderID", str(raised.exception))

	def test_marker_is_truncated_to_the_field_length(self):
		short = outbox.Operation("S", "S", "E", "Text", 10, (), ("Id",))
		self.assertEqual(outbox.prepare(short, {}, "k")["Text"], outbox.marker("k")[:10])


class TestDocumentId(unittest.TestCase):
	def test_joins_fields_and_tolerates_missing_ones(self):
		operation = outbox.OPERATIONS["Goods Movement"]
		self.assertEqual(
			outbox.document_id(operation, {"MaterialDocumentYear": 2026, "MaterialDocument": "49"}), "2026|49"
		)
		self.assertEqual(outbox.document_id(operation, {"MaterialDocument": "49"}), "|49")
		self.assertEqual(outbox.document_id(operation, {}), "|")


class TestFindExisting(unittest.TestCase):
	def test_searches_by_lookup_fields_and_marker(self):
		operation = outbox.OPERATIONS["Production Order Confirmation"]
		payload = outbox.prepare(operation, {"OrderID": "1000123"}, "k")
		fake = FakeS4HANA().on(
			"GET", "ProdnOrdConf2", ok({"results": [{"ConfirmationGroup": "1"}, {"ConfirmationGroup": "2"}]})
		)
		found = outbox.find_existing(client(fake), operation, payload)
		self.assertEqual(found, {"ConfirmationGroup": "1"})
		query = fake.requests[0]["query"]
		self.assertEqual(
			query["$filter"], f"OrderID eq '1000123' and ConfirmationText eq '{outbox.marker('k')}'"
		)
		self.assertEqual(query["$top"], "2")

	def test_goods_movement_searches_by_marker_alone(self):
		operation = outbox.OPERATIONS["Goods Movement"]
		payload = outbox.prepare(operation, {}, "k")
		fake = FakeS4HANA().on("GET", "A_MaterialDocumentHeader", ok({"results": []}))
		self.assertIsNone(outbox.find_existing(client(fake), operation, payload))
		self.assertEqual(
			fake.requests[0]["query"]["$filter"], f"MaterialDocumentHeaderText eq '{outbox.marker('k')}'"
		)


class TestSend(unittest.TestCase):
	operation = outbox.OPERATIONS["Goods Movement"]

	def payload(self):
		return outbox.prepare(self.operation, {"GoodsMovementCode": "02"}, "gr-1")

	def test_posted_document_and_response(self):
		created = {
			"MaterialDocumentYear": "2026",
			"MaterialDocument": "49",
			"to_MaterialDocumentItem": {"results": []},
		}
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "A_MaterialDocumentHeader", ok(created, 201))
		)
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "2026|49"))
		self.assertEqual(outcome.response, created)
		self.assertEqual(outcome.error, "")
		self.assertIsNone(outcome.details)

	def test_rejection_carries_details(self):
		body = sap_error(400, "M7/053", "Period closed")
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "A_MaterialDocumentHeader", body)
		)
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual(outcome.status, "Failed")
		self.assertIn("M7/053", outcome.error)
		self.assertEqual(outcome.details, [])

	def test_server_error_is_unknown_not_retry(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "A_MaterialDocumentHeader", sap_error(500, "X", "dump"))
		)
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual(outcome.status, "Unknown")

	def test_csrf_fetch_failure_is_a_retry(self):
		# Nothing was posted when the token fetch itself fails transiently.
		fake = FakeS4HANA().on("FETCH", "API_MATERIAL_DOCUMENT_SRV", Response(503, {}, b""))
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual(outcome.status, "Retry")

	def test_csrf_fetch_denied_fails(self):
		fake = FakeS4HANA().on("FETCH", "API_MATERIAL_DOCUMENT_SRV", Response(401, {}, b""))
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual(outcome.status, "Failed")

	def test_transient_failure_while_verifying_stays_unknown(self):
		fake = FakeS4HANA().on("GET", "A_MaterialDocumentHeader", Response(503, {}, b""))
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=True)
		self.assertEqual(outcome.status, "Unknown")
		self.assertEqual([r["method"] for r in fake.requests], ["GET"])

	def test_verify_then_post_when_absent(self):
		fake = (
			FakeS4HANA()
			.on("GET", "A_MaterialDocumentHeader", ok({"results": []}))
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on(
				"POST",
				"A_MaterialDocumentHeader",
				ok({"MaterialDocumentYear": "2026", "MaterialDocument": "50"}, 201),
			)
		)
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=True)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "2026|50"))
		self.assertEqual([r["method"] for r in fake.requests], ["GET", "GET", "POST"])

	def test_network_failure_on_verify_is_unknown(self):
		fake = FakeS4HANA().on("GET", "A_MaterialDocumentHeader", ConnectionRefusedError())
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=True)
		self.assertEqual(outcome.status, "Unknown")

	def test_outcome_defaults(self):
		outcome = outbox.Outcome("Retry")
		self.assertEqual(
			(outcome.document, outcome.error, outcome.details, outcome.response), ("", "", None, None)
		)


class TestRetryPolicy(unittest.TestCase):
	def test_delays_double_from_one_minute(self):
		self.assertEqual(outbox.retry_delay(0), 60)
		self.assertEqual(outbox.retry_delay(1), 60)
		self.assertEqual([outbox.retry_delay(n) for n in range(2, 8)], [120, 240, 480, 960, 1920, 3840])

	def test_delay_is_capped_and_never_overflows(self):
		self.assertEqual(outbox.retry_delay(9), 15360)
		self.assertEqual(outbox.retry_delay(10), outbox.MAX_DELAY_SECONDS)
		self.assertEqual(outbox.retry_delay(10_000), outbox.MAX_DELAY_SECONDS)

	def test_give_up_boundary(self):
		self.assertFalse(outbox.give_up(0))
		self.assertFalse(outbox.give_up(outbox.MAX_ATTEMPTS - 1))
		self.assertTrue(outbox.give_up(outbox.MAX_ATTEMPTS))
		self.assertTrue(outbox.give_up(outbox.MAX_ATTEMPTS + 5))

	def test_total_wait_before_giving_up_is_about_a_day(self):
		# 1, 2, 4 ... minutes, capped at 6 hours, over 11 waits: a posting gets most of a day to recover.
		total = sum(outbox.retry_delay(n) for n in range(1, outbox.MAX_ATTEMPTS))
		self.assertEqual(total, 73860)
		self.assertGreater(total, 12 * 3600)
		self.assertLess(total, 24 * 3600)


if __name__ == "__main__":
	unittest.main()
