# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Tests for the S/4HANA client, entity mapping, outbox rules, IDoc parsing and adapter. They need no
Frappe site and no S/4HANA system: a scripted fake answers the HTTP calls."""

import json
import unittest
from types import SimpleNamespace

from foames.foames_adapters.base import AdapterError, AdapterUnavailable
from foames.foames_adapters.s4hana import idoc, outbox
from foames.foames_adapters.s4hana.adapter import S4HANAAdapter
from foames.foames_adapters.s4hana.entities import DEFAULT_ENTITIES, spec_from_override
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.foames_adapters.s4hana.odata import (
	Connection,
	ODataClient,
	ODataError,
	Response,
	filter_expression,
	key_predicate,
)


def client(fake, **kw):
	connection = Connection(
		base_url="https://s4.example.com:44300", client="100", username="U", password="P", **kw
	)
	return ODataClient(connection, transport=fake)


class TestODataClient(unittest.TestCase):
	def test_key_predicates_quote_and_escape(self):
		self.assertEqual(key_predicate({"Product": "FG-1"}), "('FG-1')")
		self.assertEqual(key_predicate({"Product": "O'R 1"}), "('O''R%201')")
		self.assertEqual(
			key_predicate({"Material": "M1", "BatchIdentifyingPlant": "", "Batch": "B1"}),
			"(Material='M1',BatchIdentifyingPlant='',Batch='B1')",
		)

	def test_filter_expression(self):
		self.assertEqual(filter_expression({"OrderID": "1000", "Qty": 2}), "OrderID eq '1000' and Qty eq 2")

	def test_get_sends_client_format_and_basic_auth(self):
		fake = FakeS4HANA().on("GET", "A_Product", ok({"Product": "FG-1"}))
		entity = client(fake).get_entity("API_PRODUCT_SRV", "A_Product", {"Product": "FG-1"})
		self.assertEqual(entity, {"Product": "FG-1"})
		request = fake.requests[0]
		self.assertEqual(request["path"], "/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('FG-1')")
		self.assertEqual(request["query"], {"$format": "json", "sap-client": "100"})
		self.assertTrue(request["headers"]["Authorization"].startswith("Basic "))

	def test_get_returns_none_on_404(self):
		self.assertIsNone(client(FakeS4HANA()).get_entity("API_PRODUCT_SRV", "A_Product", {"Product": "X"}))

	def test_post_fetches_csrf_token_once(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_X_SRV", csrf("T1"))
			.on("POST", "Things", ok({"Id": "1"}, status=201))
		)
		c = client(fake)
		c.post("API_X_SRV", "Things", {"a": 1})
		c.post("API_X_SRV", "Things", {"a": 2})
		self.assertEqual([r["method"] for r in fake.requests], ["GET", "POST", "POST"])
		self.assertEqual(fake.requests[1]["headers"]["X-CSRF-Token"], "T1")

	def test_post_refreshes_expired_csrf_token(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_X_SRV", csrf("OLD"), once=True)
			.on("FETCH", "API_X_SRV", csrf("NEW"))
			.on("POST", "Things", Response(403, {"x-csrf-token": "Required"}, b""), once=True)
			.on("POST", "Things", ok({"Id": "1"}, status=201))
		)
		self.assertEqual(client(fake).post("API_X_SRV", "Things", {}), {"Id": "1"})
		posts = [r for r in fake.requests if r["method"] == "POST"]
		self.assertEqual([p["headers"]["X-CSRF-Token"] for p in posts], ["OLD", "NEW"])

	def test_business_rejection_is_not_transient(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_X_SRV", csrf())
			.on("POST", "Things", sap_error(400, "M7/053", "Posting period 010 2026 is not open"))
		)
		with self.assertRaises(ODataError) as raised:
			client(fake).post("API_X_SRV", "Things", {})
		self.assertFalse(raised.exception.transient)
		self.assertEqual(raised.exception.code, "M7/053")
		self.assertIn("Posting period", str(raised.exception))

	def test_server_error_on_write_may_have_been_applied(self):
		fake = FakeS4HANA().on("FETCH", "API_X_SRV", csrf()).on("POST", "Things", sap_error(503, "X", "busy"))
		with self.assertRaises(ODataError) as raised:
			client(fake).post("API_X_SRV", "Things", {})
		self.assertTrue(raised.exception.transient)
		self.assertTrue(raised.exception.maybe_applied)

	def test_network_failure_on_write_may_have_been_applied(self):
		fake = FakeS4HANA().on("FETCH", "API_X_SRV", csrf()).on("POST", "Things", TimeoutError("timed out"))
		with self.assertRaises(ODataError) as raised:
			client(fake).post("API_X_SRV", "Things", {})
		self.assertTrue(raised.exception.transient and raised.exception.maybe_applied)

	def test_oauth_token_is_fetched_and_cached(self):
		token = Response(200, {}, json.dumps({"access_token": "abc", "expires_in": 3600}).encode())
		fake = FakeS4HANA().on("POST", "/oauth/token", token).on("GET", "A_Product", ok({"Product": "1"}))
		c = client(
			fake,
			auth="OAuth 2.0 Client Credentials",
			token_url="https://s4.example.com/oauth/token",
			client_id="id",
			client_secret="secret",
		)
		c.get_entity("API_PRODUCT_SRV", "A_Product", {"Product": "1"})
		c.get_entity("API_PRODUCT_SRV", "A_Product", {"Product": "1"})
		self.assertEqual(len([r for r in fake.requests if "oauth" in r["path"]]), 1)
		self.assertEqual(fake.requests[-1]["headers"]["Authorization"], "Bearer abc")


class TestEntities(unittest.TestCase):
	def test_batch_key_with_and_without_plant(self):
		spec = DEFAULT_ENTITIES["Batch"]
		self.assertEqual(
			spec.keys_for("M1|B1"), {"Material": "M1", "BatchIdentifyingPlant": "", "Batch": "B1"}
		)
		self.assertEqual(
			spec.keys_for("M1|1010|B1"), {"Material": "M1", "BatchIdentifyingPlant": "1010", "Batch": "B1"}
		)
		self.assertEqual(
			spec.external_id_for({"Material": "M1", "BatchIdentifyingPlant": "", "Batch": "B1"}), "M1|B1"
		)
		self.assertEqual(
			spec.external_id_for({"Material": "M1", "BatchIdentifyingPlant": "1010", "Batch": "B1"}),
			"M1|1010|B1",
		)
		with self.assertRaises(ValueError):
			spec.keys_for("M1")

	def test_item_label_prefers_session_language(self):
		entity = {
			"Product": "FG-1",
			"to_Description": {
				"results": [
					{"Language": "DE", "ProductDescription": "Schaum"},
					{"Language": "EN", "ProductDescription": "Foam"},
				]
			},
		}
		spec = DEFAULT_ENTITIES["Item"]
		self.assertEqual(spec.label_for(entity, "EN"), "Foam")
		self.assertEqual(spec.label_for(entity, "FR"), "Schaum")
		self.assertEqual(spec.label_for({"Product": "FG-2"}), "FG-2")

	def test_override_row(self):
		spec = spec_from_override(
			{
				"service": "API_PLANT_SRV",
				"entity_set": "A_Plant",
				"key_fields": "Plant",
				"label_field": "PlantName",
			}
		)
		self.assertEqual(spec.keys_for("1010"), {"Plant": "1010"})
		with self.assertRaises(ValueError):
			spec_from_override({"service": "S", "entity_set": "", "key_fields": "K"})


class TestOutbox(unittest.TestCase):
	operation = outbox.OPERATIONS["Production Order Confirmation"]

	def payload(self):
		return outbox.prepare(
			self.operation, {"OrderID": "1000123", "ConfirmationYieldQuantity": "10"}, "seg-1:mix:done"
		)

	def test_marker_is_stable_and_fits_material_document_text(self):
		self.assertEqual(outbox.marker("k"), outbox.marker("k"))
		self.assertNotEqual(outbox.marker("k"), outbox.marker("k2"))
		self.assertLessEqual(len(outbox.marker("k")), 25)
		self.assertEqual(self.payload()["ConfirmationText"], outbox.marker("seg-1:mix:done"))

	def test_prepare_requires_lookup_fields(self):
		with self.assertRaises(ValueError):
			outbox.prepare(self.operation, {"ConfirmationYieldQuantity": "1"}, "k")

	def test_posted(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", ok({"ConfirmationGroup": "77", "ConfirmationCount": "1"}, 201))
		)
		result = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual((result.status, result.document), ("Posted", "77|1"))

	def test_rejection_fails_without_retry(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", sap_error(400, "RU/100", "Order is locked"))
		)
		result = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual(result.status, "Failed")
		self.assertIn("locked", result.error)

	def test_timeout_becomes_unknown_then_finds_existing_instead_of_reposting(self):
		fake = FakeS4HANA().on("FETCH", "CONFIRMATION", csrf()).on("POST", "ProdnOrdConf2", TimeoutError("t"))
		payload = self.payload()
		first = outbox.send(client(fake), self.operation, payload, verify_first=False)
		self.assertEqual(first.status, "Unknown")

		# S/4HANA did post it before the connection dropped.
		existing = {"results": [{"ConfirmationGroup": "77", "ConfirmationCount": "1"}]}
		fake = FakeS4HANA().on("GET", "ProdnOrdConf2", ok(existing))
		second = outbox.send(client(fake), self.operation, payload, verify_first=True)
		self.assertEqual((second.status, second.document), ("Posted", "77|1"))
		self.assertEqual([r["method"] for r in fake.requests], ["GET"])
		self.assertIn(
			f"ConfirmationText eq '{payload['ConfirmationText']}'", fake.requests[0]["query"]["$filter"]
		)

	def test_verified_absent_posts_again(self):
		fake = (
			FakeS4HANA()
			.on("GET", "ProdnOrdConf2", ok({"results": []}))
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", ok({"ConfirmationGroup": "78", "ConfirmationCount": "1"}, 201))
		)
		result = outbox.send(client(fake), self.operation, self.payload(), verify_first=True)
		self.assertEqual((result.status, result.document), ("Posted", "78|1"))

	def test_throttled_send_is_retried(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", Response(429, {}, b""))
		)
		self.assertEqual(outbox.send(client(fake), self.operation, self.payload(), False).status, "Retry")

	def test_rejected_login_is_retried_not_failed(self):
		# A 401 cannot have applied the posting; failing it would hold the whole sequence group until
		# someone requeues it, so it retries until the credentials are fixed.
		fake = (
			FakeS4HANA()
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", Response(401, {}, b"Unauthorized"))
		)
		result = outbox.send(client(fake), self.operation, self.payload(), False)
		self.assertEqual(result.status, "Retry")
		self.assertIn("401", result.error)

	def test_rejected_oauth_token_is_retried(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", Response(401, {}, b"invalid_client"))
		c = client(
			fake,
			auth="OAuth 2.0 Client Credentials",
			token_url="https://s4.example.com/oauth/token",
			client_id="foames",
			client_secret="rotated",
		)
		self.assertEqual(outbox.send(c, self.operation, self.payload(), False).status, "Retry")

	def test_backoff(self):
		self.assertEqual([outbox.retry_delay(n) for n in (1, 2, 3)], [60, 120, 240])
		self.assertEqual(outbox.retry_delay(20), outbox.MAX_DELAY_SECONDS)
		self.assertFalse(outbox.give_up(outbox.MAX_ATTEMPTS - 1))
		self.assertTrue(outbox.give_up(outbox.MAX_ATTEMPTS))


LOIPRO = b"""<?xml version="1.0" encoding="UTF-8"?>
<LOIPRO01>
 <IDOC BEGIN="1">
  <EDI_DC40 SEGMENT="1">
   <DOCNUM>0000000000123456</DOCNUM><IDOCTYP>LOIPRO01</IDOCTYP><MESTYP>LOIPRO</MESTYP>
   <SNDPRN>S4HCLNT100</SNDPRN><RCVPRN>FOAMES</RCVPRN>
  </EDI_DC40>
  <E1AFKOL SEGMENT="1">
   <AUFNR>000001000123</AUFNR><AUART>PP01</AUART><MATNR>FG-1</MATNR><WERKS>1010</WERKS>
   <GAMNG>100.000</GAMNG><GMEIN>KG</GMEIN>
   <E1AFFLL SEGMENT="1">
    <E1AFVOL SEGMENT="1"><VORNR>0010</VORNR><ARBPL>MIX01</ARBPL><LTXA1>Mix</LTXA1></E1AFVOL>
    <E1AFVOL SEGMENT="1"><VORNR>0020</VORNR><ARBPL>CURE01</ARBPL><LTXA1>Cure</LTXA1></E1AFVOL>
   </E1AFFLL>
  </E1AFKOL>
 </IDOC>
</LOIPRO01>"""


class TestIDoc(unittest.TestCase):
	def test_parses_order_download(self):
		[parsed] = idoc.parse(LOIPRO)
		self.assertEqual(
			(parsed.number, parsed.message_type, parsed.sender), ("123456", "LOIPRO", "S4HCLNT100")
		)
		summary = idoc.summarize(parsed)
		self.assertEqual(summary["reference_type"], "Work Order")
		self.assertEqual(summary["external_id"], "1000123")
		self.assertEqual([op["operation"] for op in summary["operations"]], ["0010", "0020"])

	def test_refuses_doctype(self):
		with self.assertRaises(idoc.IDocError):
			idoc.parse(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')

	def test_refuses_missing_control_record(self):
		with self.assertRaises(idoc.IDocError):
			idoc.parse(b"<LOIPRO01><IDOC><E1AFKOL/></IDOC></LOIPRO01>")

	def test_unknown_message_type_has_empty_summary(self):
		xml = LOIPRO.replace(b"<MESTYP>LOIPRO</MESTYP>", b"<MESTYP>ZFOO</MESTYP>")
		self.assertEqual(idoc.summarize(idoc.parse(xml)[0]), {})


class FakeSettings(SimpleNamespace):
	def entity_specs(self):
		return dict(DEFAULT_ENTITIES)

	def client(self, transport=None):
		return client(transport)


class TestAdapter(unittest.TestCase):
	def adapter(self, fake, enabled=1):
		return S4HANAAdapter(
			FakeSettings(enabled=enabled, base_url="https://s4", language="EN"), transport=fake
		)

	def test_resolves_batch(self):
		fake = FakeS4HANA().on(
			"GET", "Batch(", ok({"Material": "M1", "BatchIdentifyingPlant": "", "Batch": "B1"})
		)
		resolved = self.adapter(fake).resolve("Batch", "M1|B1")
		self.assertEqual((resolved.external_id, resolved.label), ("M1|B1", "B1"))
		self.assertIn("Batch(Material='M1',BatchIdentifyingPlant='',Batch='B1')", fake.requests[0]["path"])

	def test_missing_record(self):
		self.assertIsNone(self.adapter(FakeS4HANA()).resolve("Work Order", "999"))
		self.assertIsNone(self.adapter(FakeS4HANA()).resolve("Batch", "too|many|parts|here"))

	def test_unmapped_types_are_unsupported_until_configured(self):
		adapter = self.adapter(FakeS4HANA())
		self.assertTrue(adapter.supports("Item"))
		self.assertFalse(adapter.supports("Unit of Measure"))

	def test_disabled_adapter_is_unavailable(self):
		with self.assertRaises(AdapterUnavailable):
			self.adapter(FakeS4HANA(), enabled=0).resolve("Item", "FG-1")

	def test_unreachable_system_is_unavailable_not_missing(self):
		fake = FakeS4HANA().on("GET", "A_Product", ConnectionRefusedError("refused"))
		with self.assertRaises(AdapterUnavailable):
			self.adapter(fake).resolve("Item", "FG-1")

	def test_bad_request_is_an_adapter_error(self):
		fake = FakeS4HANA().on("GET", "A_Product", sap_error(400, "X", "bad"))
		with self.assertRaises(AdapterError):
			self.adapter(fake).resolve("Item", "FG-1")
