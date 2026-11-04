# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The shared outbox rules: the generic request in its three idempotency kinds, profile
operations, the verify-first search and the outcome of every kind of answer. No Frappe site needed."""

import unittest

from foames.foames_adapters.mes import outbox
from foames.foames_adapters.mes.fake import FakeMES, mes_error, no_content, ok
from foames.foames_adapters.mes.profile import CLIENT_REFERENCE, GENERIC_OPERATION, MANUAL, UPSERT, Operation
from foames.foames_adapters.mes.rest import Connection, RestClient

MANUAL_REQUEST = {"method": "POST", "path": "sfc/v1/sfcStart", "body": {"plant": "1010", "sfc": "S1"}}
UPSERT_REQUEST = {"method": "PUT", "path": "equipment/E1/status", "body": {"status": "RUNNING"}}
REFERENCED_REQUEST = {
	"method": "POST",
	"path": "tables/t1/records",
	"body": {"order": "1000123", "qty": 5},
	"reference_field": "externalRef",
	"lookup_path": "tables/t1/records",
	"lookup_query": "externalRef",
}
CONFIRM = Operation(
	label="Confirm",
	method="POST",
	path="confirmations",
	required=("order",),
	idempotency=CLIENT_REFERENCE,
	reference_field="clientReference",
	lookup_path="confirmations",
	lookup_fields=("order",),
	document_path="confirmation.id",
)


def client(fake):
	return RestClient(Connection(base_url="https://mes.example/api"), transport=fake)


class TestEffective(unittest.TestCase):
	def test_generic_request_kinds(self):
		self.assertEqual(outbox.effective(GENERIC_OPERATION, MANUAL_REQUEST).idempotency, MANUAL)
		self.assertEqual(outbox.effective(GENERIC_OPERATION, UPSERT_REQUEST).idempotency, UPSERT)
		self.assertEqual(
			outbox.effective(GENERIC_OPERATION, {**UPSERT_REQUEST, "idempotent": False}).idempotency, MANUAL
		)
		self.assertEqual(
			outbox.effective(GENERIC_OPERATION, {**MANUAL_REQUEST, "idempotent": True}).idempotency, UPSERT
		)
		self.assertEqual(
			outbox.effective(GENERIC_OPERATION, REFERENCED_REQUEST).idempotency, CLIENT_REFERENCE
		)
		self.assertEqual(outbox.effective(GENERIC_OPERATION, {"path": "x"}).method, "POST")

	def test_profile_operation_is_itself(self):
		self.assertIs(outbox.effective(CONFIRM, {"order": "1"}), CONFIRM)


class TestPrepare(unittest.TestCase):
	def test_generic_request_is_checked(self):
		prepared = outbox.prepare(GENERIC_OPERATION, MANUAL_REQUEST, "k")
		self.assertEqual(prepared, MANUAL_REQUEST)
		self.assertIsNot(prepared, MANUAL_REQUEST)
		for bad in (
			{"path": "x"},
			{"method": "POST"},
			{"method": "GET", "path": "x"},
			{"method": "FETCH", "path": "x"},
		):
			with self.assertRaises(ValueError, msg=bad):
				outbox.prepare(GENERIC_OPERATION, bad, "k")

	def test_generic_reference_goes_into_the_body(self):
		prepared = outbox.prepare(GENERIC_OPERATION, REFERENCED_REQUEST, "k")
		self.assertEqual(prepared["body"]["externalRef"], outbox.marker("k"))
		self.assertNotIn("externalRef", REFERENCED_REQUEST["body"])
		with self.assertRaises(ValueError):
			outbox.prepare(GENERIC_OPERATION, {**REFERENCED_REQUEST, "body": [1]}, "k")

	def test_profile_operation_reference_and_required(self):
		prepared = outbox.prepare(CONFIRM, {"order": "1", "qty": 2}, "k")
		self.assertEqual(prepared["clientReference"], outbox.marker("k"))
		with self.assertRaises(ValueError) as raised:
			outbox.prepare(CONFIRM, {"qty": 2}, "k")
		self.assertIn("order", str(raised.exception))

	def test_marker_shape(self):
		mark = outbox.marker("any key")
		self.assertEqual(len(mark), 23)
		self.assertTrue(mark.startswith(outbox.MARKER_PREFIX))
		int(mark[len(outbox.MARKER_PREFIX) :], 16)


class TestDocumentIds(unittest.TestCase):
	def test_from_answer_path_or_fallback(self):
		self.assertEqual(outbox.document_id(CONFIRM, {}, {"confirmation": {"id": 77}}), "77")
		self.assertEqual(outbox.document_id(CONFIRM, {}, {"other": 1}), "")
		self.assertEqual(outbox.document_id(GENERIC_OPERATION, UPSERT_REQUEST, None), "equipment/E1/status")
		self.assertEqual(
			outbox.document_id(
				GENERIC_OPERATION, {**MANUAL_REQUEST, "document_path": "sfc.id"}, {"sfc": {"id": "S1"}}
			),
			"S1",
		)
		self.assertEqual(outbox.document_id(GENERIC_OPERATION, MANUAL_REQUEST, {"x": 1}), "")


class TestSend(unittest.TestCase):
	def test_generic_request_is_sent_with_its_body(self):
		fake = FakeMES().on("POST", "/sfc/v1/sfcStart", ok({"id": "s1"}))
		outcome = outbox.send(client(fake), GENERIC_OPERATION, MANUAL_REQUEST, verify_first=False)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "s1"))
		self.assertEqual(fake.requests[-1]["body"], MANUAL_REQUEST["body"])

	def test_rejection_is_final(self):
		fake = FakeMES().on("POST", "/sfc", mes_error(400, "SFC not found"))
		outcome = outbox.send(client(fake), GENERIC_OPERATION, MANUAL_REQUEST, False)
		self.assertEqual(outcome.status, "Failed")
		self.assertIn("SFC not found", outcome.error)
		self.assertFalse(outcome.halt)

	def test_manual_unclear_answer_halts(self):
		for answer in (mes_error(503, "down"), TimeoutError("t")):
			fake = FakeMES().on("POST", "/sfc", answer)
			outcome = outbox.send(client(fake), GENERIC_OPERATION, MANUAL_REQUEST, False)
			self.assertEqual((outcome.status, outcome.halt), ("Unknown", True), msg=answer)
			self.assertIn("cannot be checked automatically", outcome.error)

	def test_manual_clear_transient_answer_retries(self):
		for answer in (mes_error(429, "slow"), mes_error(401, "expired")):
			fake = FakeMES().on("POST", "/sfc", answer)
			outcome = outbox.send(client(fake), GENERIC_OPERATION, MANUAL_REQUEST, False)
			self.assertEqual((outcome.status, outcome.halt), ("Retry", False), msg=answer)
		# After an earlier unclear answer, a person requeued it: it is sent, and still halts if unclear again.
		fake = FakeMES().on("POST", "/sfc", mes_error(429, "slow"))
		self.assertEqual(outbox.send(client(fake), GENERIC_OPERATION, MANUAL_REQUEST, True).halt, True)

	def test_upsert_is_sent_again_whatever_happened(self):
		for answer in (mes_error(503, "down"), TimeoutError("t"), mes_error(429, "slow")):
			fake = FakeMES().on("PUT", "/equipment", answer)
			outcome = outbox.send(client(fake), GENERIC_OPERATION, UPSERT_REQUEST, True)
			self.assertEqual((outcome.status, outcome.halt), ("Retry", False), msg=answer)
		fake = FakeMES().on("PUT", "/equipment", no_content())
		outcome = outbox.send(client(fake), GENERIC_OPERATION, UPSERT_REQUEST, True)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "equipment/E1/status"))
		self.assertEqual([r["method"] for r in fake.requests], ["PUT"])

	def test_client_reference_verify_first(self):
		prepared = outbox.prepare(GENERIC_OPERATION, REFERENCED_REQUEST, "k")
		existing = {"id": "r7", "externalRef": outbox.marker("k")}
		fake = FakeMES().on(
			"GET", "/tables/t1/records", ok({"records": [{"id": "r6", "externalRef": "x"}, existing]})
		)
		outcome = outbox.send(client(fake), GENERIC_OPERATION, prepared, verify_first=True)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "r7"))
		self.assertEqual(fake.requests[-1]["query"], {"externalRef": outbox.marker("k")})
		self.assertFalse([r for r in fake.requests if r["method"] == "POST"])

	def test_client_reference_posts_when_nothing_matches(self):
		prepared = outbox.prepare(GENERIC_OPERATION, REFERENCED_REQUEST, "k")
		fake = FakeMES().on("GET", "/tables", ok([])).on("POST", "/tables", ok({"id": "r8"}, 201))
		self.assertEqual(outbox.send(client(fake), GENERIC_OPERATION, prepared, True).document, "r8")
		self.assertEqual(fake.requests[-1]["body"]["externalRef"], outbox.marker("k"))

	def test_client_reference_outcomes(self):
		prepared = outbox.prepare(GENERIC_OPERATION, REFERENCED_REQUEST, "k")
		for answer, verify, expected in (
			(mes_error(503, "down"), False, "Unknown"),
			(TimeoutError("t"), False, "Unknown"),
			(mes_error(429, "slow"), False, "Retry"),
			(mes_error(429, "slow"), True, "Unknown"),
			(mes_error(400, "bad"), False, "Failed"),
		):
			fake = FakeMES().on("GET", "/tables", ok([])).on("POST", "/tables", answer)
			outcome = outbox.send(client(fake), GENERIC_OPERATION, prepared, verify)
			self.assertEqual((outcome.status, outcome.halt), (expected, False), msg=(answer, verify))

	def test_profile_operation_search_uses_lookup_fields_and_filters_client_side(self):
		prepared = outbox.prepare(CONFIRM, {"order": "1000123", "qty": 2}, "k")
		fake = FakeMES().on(
			"GET",
			"/confirmations",
			ok({"value": [{"clientReference": outbox.marker("k"), "confirmation": {"id": 5}}]}),
		)
		outcome = outbox.send(client(fake), CONFIRM, prepared, verify_first=True)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "5"))
		self.assertEqual(fake.requests[-1]["query"], {"order": "1000123"})

	def test_failed_search_is_unknown(self):
		prepared = outbox.prepare(CONFIRM, {"order": "1"}, "k")
		fake = FakeMES().on("GET", "/confirmations", mes_error(503, "down"))
		self.assertEqual(outbox.send(client(fake), CONFIRM, prepared, True).status, "Unknown")


class TestRetryPolicy(unittest.TestCase):
	def test_backoff_and_give_up(self):
		self.assertEqual([outbox.retry_delay(n) for n in (0, 1, 2, 3)], [60, 60, 120, 240])
		self.assertEqual(outbox.retry_delay(50), outbox.MAX_DELAY_SECONDS)
		self.assertFalse(outbox.give_up(outbox.MAX_ATTEMPTS - 1))
		self.assertTrue(outbox.give_up(outbox.MAX_ATTEMPTS))


if __name__ == "__main__":
	unittest.main()
