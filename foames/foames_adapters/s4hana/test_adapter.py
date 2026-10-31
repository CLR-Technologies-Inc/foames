# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The S/4HANA adapter against the scripted fake: which request each reference type sends and how
every answer maps onto the adapter contract. No Frappe site needed."""

import unittest
from types import SimpleNamespace

from foames.foames_adapters.base import (
	AdapterError,
	AdapterUnavailable,
	ResolvedReference,
	UnsupportedReferenceType,
)
from foames.foames_adapters.s4hana.adapter import ADAPTER_KEY, S4HANAAdapter
from foames.foames_adapters.s4hana.entities import DEFAULT_ENTITIES, spec_from_override
from foames.foames_adapters.s4hana.fake import FakeS4HANA, ok, sap_error
from foames.foames_adapters.s4hana.odata import Connection, ODataClient, Response


class Settings(SimpleNamespace):
	"""Stands in for S4HANA Settings: the same three methods the adapter uses."""

	overrides = {}  # noqa: RUF012

	def entity_specs(self):
		specs = dict(DEFAULT_ENTITIES)
		for reference_type, row in self.overrides.items():
			specs[reference_type] = spec_from_override(row)
		return specs

	def client(self, transport=None):
		return ODataClient(
			Connection(base_url=self.base_url, client="100", language=self.language), transport=transport
		)


def adapter(fake=None, enabled=1, base_url="https://s4", language="EN", overrides=None):
	settings = Settings(enabled=enabled, base_url=base_url, language=language)
	settings.overrides = overrides or {}
	return S4HANAAdapter(settings, transport=fake or FakeS4HANA())


class TestContract(unittest.TestCase):
	def test_key_and_label(self):
		self.assertEqual((S4HANAAdapter.key, ADAPTER_KEY), ("S4HANA", "S4HANA"))
		self.assertEqual(adapter().label, "SAP S/4HANA")

	def test_reference_map_follows_the_settings(self):
		self.assertEqual(adapter().reference_map["Item"], "A_Product")
		with_location = adapter(
			overrides={
				"Location": {"service": "API_PLANT_SRV", "entity_set": "A_Plant", "key_fields": "Plant"}
			}
		)
		self.assertEqual(with_location.reference_map["Location"], "A_Plant")
		self.assertTrue(with_location.supports("Location"))

	def test_availability_needs_enabled_and_a_url(self):
		self.assertTrue(adapter().is_available())
		self.assertFalse(adapter(enabled=0).is_available())
		self.assertFalse(adapter(base_url="").is_available())

	def test_unsupported_type_is_refused_before_any_request(self):
		fake = FakeS4HANA()
		with self.assertRaises(UnsupportedReferenceType):
			adapter(fake).resolve("Serial Number", "SN1")
		self.assertEqual(fake.requests, [])


class TestResolve(unittest.TestCase):
	def test_item_expands_descriptions_and_picks_the_language(self):
		entity = {
			"Product": "FG-1",
			"to_Description": {
				"results": [
					{"Language": "DE", "ProductDescription": "Schaum"},
					{"Language": "EN", "ProductDescription": "Foam"},
				]
			},
		}
		fake = FakeS4HANA().on("GET", "A_Product", ok(entity))
		resolved = adapter(fake, language="DE").resolve("Item", "FG-1")
		self.assertIsInstance(resolved, ResolvedReference)
		self.assertEqual(
			(resolved.reference_type, resolved.external_id, resolved.label), ("Item", "FG-1", "Schaum")
		)
		self.assertEqual(
			resolved.data,
			{"service": "API_PRODUCT_SRV", "entity_set": "A_Product", "keys": {"Product": "FG-1"}},
		)
		request = fake.requests[0]
		self.assertEqual(request["path"], "/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('FG-1')")
		self.assertEqual(request["query"]["$expand"], "to_Description")
		self.assertEqual(request["headers"]["Accept-Language"], "de")

	def test_missing_language_falls_back_to_english_texts(self):
		entity = {
			"Product": "FG-1",
			"to_Description": {"results": [{"Language": "EN", "ProductDescription": "Foam"}]},
		}
		fake = FakeS4HANA().on("GET", "A_Product", ok(entity))
		self.assertEqual(adapter(fake, language="").resolve("Item", "FG-1").label, "Foam")

	def test_work_order_external_id_comes_back_from_the_entity(self):
		fake = FakeS4HANA().on(
			"GET", "A_ProductionOrder_2", ok({"ManufacturingOrder": "000001000123", "Material": "FG-1"})
		)
		resolved = adapter(fake).resolve("Work Order", "1000123")
		self.assertEqual((resolved.external_id, resolved.label), ("000001000123", "FG-1"))
		self.assertIn("A_ProductionOrder_2('1000123')", fake.requests[0]["path"])
		self.assertNotIn("$expand", fake.requests[0]["query"])

	def test_entity_without_key_values_keeps_the_requested_id(self):
		fake = FakeS4HANA().on("GET", "A_ProductionOrder_2", ok({"Material": "FG-1"}))
		self.assertEqual(adapter(fake).resolve("Work Order", "1000123").external_id, "1000123")

	def test_stock_movement_composite_key(self):
		fake = FakeS4HANA().on(
			"GET",
			"A_MaterialDocumentHeader",
			ok(
				{"MaterialDocumentYear": "2026", "MaterialDocument": "49", "MaterialDocumentHeaderText": "GR"}
			),
		)
		resolved = adapter(fake).resolve("Stock Movement", "2026|49")
		self.assertEqual((resolved.external_id, resolved.label), ("2026|49", "GR"))
		self.assertIn(
			"A_MaterialDocumentHeader(MaterialDocumentYear='2026',MaterialDocument='49')",
			fake.requests[0]["path"],
		)

	def test_id_that_cannot_be_a_key_is_missing_without_a_request(self):
		fake = FakeS4HANA()
		self.assertIsNone(adapter(fake).resolve("Stock Movement", "49"))
		self.assertEqual(fake.requests, [])

	def test_404_is_missing(self):
		self.assertIsNone(
			adapter(FakeS4HANA().on("GET", "A_Product", Response(404, {}, b""))).resolve("Item", "X")
		)

	def test_status_mapping(self):
		for status, expected in (
			(401, AdapterUnavailable),
			(403, AdapterUnavailable),
			(429, AdapterUnavailable),
			(500, AdapterUnavailable),
			(503, AdapterUnavailable),
			(400, AdapterError),
			(409, AdapterError),
		):
			fake = FakeS4HANA().on("GET", "A_Product", sap_error(status, "C", f"status {status}"))
			with self.assertRaises(expected, msg=status) as raised:
				adapter(fake).resolve("Item", "FG-1")
			self.assertIn(f"status {status}", str(raised.exception))
			self.assertIn("SAP S/4HANA", str(raised.exception))

	def test_network_errors_are_unavailable(self):
		for error in (TimeoutError(), ConnectionRefusedError(), OSError("dns")):
			fake = FakeS4HANA().on("GET", "A_Product", error)
			with self.assertRaises(AdapterUnavailable):
				adapter(fake).resolve("Item", "FG-1")

	def test_overridden_entity_is_used(self):
		fake = FakeS4HANA().on("GET", "A_Plant", ok({"Plant": "1010", "PlantName": "Hamburg"}))
		override = {
			"service": "API_PLANT_SRV",
			"entity_set": "A_Plant",
			"key_fields": "Plant",
			"label_field": "PlantName",
		}
		resolved = adapter(fake, overrides={"Location": override}).resolve("Location", "1010")
		self.assertEqual(resolved.label, "Hamburg")
		self.assertIn("/API_PLANT_SRV/A_Plant('1010')", fake.requests[0]["path"])

	def test_fetch_can_be_called_directly_with_the_entity_set(self):
		fake = FakeS4HANA().on("GET", "A_Product", ok({"Product": "FG-1"}))
		resolved = adapter(fake).fetch("A_Product", "Item", "FG-1")
		self.assertEqual(resolved.label, "FG-1")


if __name__ == "__main__":
	unittest.main()
