# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Insights Hub adapter against the scripted fake: which request each reference type sends and
how every answer maps onto the adapter contract. No Frappe site needed."""

import unittest
from types import SimpleNamespace

from foames.foames_adapters.base import (
	AdapterError,
	AdapterUnavailable,
	ResolvedReference,
	UnsupportedReferenceType,
)
from foames.foames_adapters.insights_hub import ADAPTER_KEY
from foames.foames_adapters.insights_hub.adapter import InsightsHubAdapter, job_id, parse_job
from foames.foames_adapters.insights_hub.entities import DEFAULT_ENTITIES, spec_from_override
from foames.foames_adapters.insights_hub.fake import FakeInsightsHub, hub_error, ok, page
from foames.foames_adapters.insights_hub.rest import Connection, Response, RestClient

ASSET = {"assetId": "a1", "name": "Press 1", "typeId": "plant1.Press", "location": {"locality": "Hamburg"}}
MATERIALS = {
	"service": "opcenterintelligence/v1",
	"resource": "materials",
	"key_fields": "materialNumber",
	"label_field": "description",
}
ORDERS = {
	"service": "opcenterintelligence/v1",
	"resource": "orders",
	"key_fields": "orderNumber",
	"lookup": "Filter",
	"label_field": "material.description",
}


class Settings(SimpleNamespace):
	"""Stands in for Insights Hub Settings: the methods the adapter uses."""

	overrides = {}  # noqa: RUF012

	def entity_specs(self):
		specs = dict(DEFAULT_ENTITIES)
		for reference_type, row in self.overrides.items():
			specs[reference_type] = spec_from_override(row)
		return specs

	def client(self, transport=None):
		return RestClient(
			Connection(gateway_url=self.gateway_url, client_id="c", client_secret="s", app_name="foames"),
			transport=transport,
		)


def adapter(fake=None, enabled=1, gateway_url="https://gw", overrides=None):
	settings = Settings(enabled=enabled, gateway_url=gateway_url)
	settings.overrides = overrides or {}
	return InsightsHubAdapter(settings, transport=fake or FakeInsightsHub())


def requests_of(fake, method):
	return [r for r in fake.requests if r["method"] == method and "oauth/token" not in r["path"]]


class TestContract(unittest.TestCase):
	def test_key_and_label(self):
		self.assertEqual((InsightsHubAdapter.key, ADAPTER_KEY), ("INSIGHTS_HUB", "INSIGHTS_HUB"))
		self.assertEqual(adapter().label, "Siemens Insights Hub")

	def test_reference_map_follows_the_settings(self):
		plain = adapter()
		self.assertEqual(
			plain.reference_map, {"Workstation": "assets", "Location": "assets", "Job Card": "Job"}
		)
		mapped = adapter(overrides={"Item": MATERIALS})
		self.assertEqual(mapped.reference_map["Item"], "materials")
		self.assertTrue(mapped.supports("Item"))
		self.assertFalse(plain.supports("Item"))

	def test_availability_needs_enabled_and_a_gateway(self):
		self.assertTrue(adapter().is_available())
		self.assertFalse(adapter(enabled=0).is_available())
		self.assertFalse(adapter(gateway_url="").is_available())

	def test_unsupported_type_is_refused_before_any_request(self):
		fake = FakeInsightsHub()
		with self.assertRaises(UnsupportedReferenceType):
			adapter(fake).resolve("Batch", "B1")
		self.assertEqual(fake.requests, [])


class TestResolve(unittest.TestCase):
	def test_workstation_is_an_asset_by_path(self):
		fake = FakeInsightsHub().on("GET", "/assets/a1", ok(ASSET))
		resolved = adapter(fake).resolve("Workstation", "a1")
		self.assertIsInstance(resolved, ResolvedReference)
		self.assertEqual(
			(resolved.reference_type, resolved.external_id, resolved.label), ("Workstation", "a1", "Press 1")
		)
		self.assertEqual(
			resolved.data, {"service": "assetmanagement/v3", "resource": "assets", "keys": {"assetId": "a1"}}
		)
		get = requests_of(fake, "GET")[0]
		self.assertEqual(get["path"], "/api/assetmanagement/v3/assets/a1")
		self.assertEqual(get["headers"]["Authorization"], "Bearer T1")

	def test_asset_id_is_url_encoded(self):
		fake = FakeInsightsHub().on("GET", "/assets/", ok(ASSET))
		adapter(fake).resolve("Location", "a/1 x")
		self.assertTrue(requests_of(fake, "GET")[0]["url"].endswith("/assets/a%2F1%20x"))

	def test_missing_asset_is_none(self):
		self.assertIsNone(adapter(FakeInsightsHub()).resolve("Workstation", "nope"))
		fake = FakeInsightsHub().on("GET", "/assets/a1", ok([1, 2]))
		self.assertIsNone(adapter(fake).resolve("Workstation", "a1"))

	def test_empty_id_is_missing_without_a_request(self):
		fake = FakeInsightsHub()
		self.assertIsNone(adapter(fake).resolve("Workstation", " "))
		self.assertEqual(fake.requests, [])

	def test_mapped_resource_by_path(self):
		fake = FakeInsightsHub().on(
			"GET", "/materials/FG-1", ok({"materialNumber": "FG-1", "description": "Foam block"})
		)
		resolved = adapter(fake, overrides={"Item": MATERIALS}).resolve("Item", "FG-1")
		self.assertEqual((resolved.external_id, resolved.label), ("FG-1", "Foam block"))
		self.assertEqual(requests_of(fake, "GET")[0]["path"], "/api/opcenterintelligence/v1/materials/FG-1")

	def test_mapped_resource_by_filter(self):
		order = {"orderNumber": "1000123", "material": {"description": "Foam block"}}
		fake = FakeInsightsHub().on("GET", "/orders", page([order], "orders"))
		resolved = adapter(fake, overrides={"Work Order": ORDERS}).resolve("Work Order", "1000123")
		self.assertEqual((resolved.external_id, resolved.label), ("1000123", "Foam block"))
		get = requests_of(fake, "GET")[0]
		self.assertEqual(get["path"], "/api/opcenterintelligence/v1/orders")
		self.assertEqual(get["query"]["filter"], {"orderNumber": "1000123"})
		self.assertEqual(get["query"]["size"], "2")
		empty = FakeInsightsHub().on("GET", "/orders", page([], "orders"))
		self.assertIsNone(adapter(empty, overrides={"Work Order": ORDERS}).resolve("Work Order", "1000123"))

	def test_composite_filter_key(self):
		batches = {
			"service": "oi/v1",
			"resource": "batches",
			"key_fields": "material,batch",
			"lookup": "Filter",
			"label_field": "batch",
		}
		fake = FakeInsightsHub().on("GET", "/batches", page([{"material": "FG-1", "batch": "B7"}], "batches"))
		resolved = adapter(fake, overrides={"Batch": batches}).resolve("Batch", "FG-1|B7")
		self.assertEqual((resolved.external_id, resolved.label), ("FG-1|B7", "B7"))
		self.assertEqual(requests_of(fake, "GET")[0]["query"]["filter"], {"material": "FG-1", "batch": "B7"})
		no_request = FakeInsightsHub()
		self.assertIsNone(adapter(no_request, overrides={"Batch": batches}).resolve("Batch", "B7"))
		self.assertEqual(no_request.requests, [])

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
			fake = FakeInsightsHub().on("GET", "/assets/a1", hub_error(status, "C", f"status {status}"))
			with self.assertRaises(expected, msg=status) as raised:
				adapter(fake).resolve("Workstation", "a1")
			self.assertIn(f"status {status}", str(raised.exception))
			self.assertIn("Siemens Insights Hub", str(raised.exception))

	def test_token_failure_is_unavailable(self):
		fake = FakeInsightsHub().on("POST", "oauth/token", hub_error(401, "C", "bad credentials"))
		with self.assertRaises(AdapterUnavailable):
			adapter(fake).resolve("Workstation", "a1")

	def test_network_errors_are_unavailable(self):
		for error in (TimeoutError(), ConnectionRefusedError(), OSError("dns")):
			fake = FakeInsightsHub().on("GET", "/assets/a1", error)
			with self.assertRaises(AdapterUnavailable):
				adapter(fake).resolve("Workstation", "a1")


class TestJobs(unittest.TestCase):
	def test_parse_and_format(self):
		self.assertEqual(parse_job("1000123|0010"), ("1000123", "0010"))
		self.assertEqual(parse_job(" 1000123 "), ("1000123", ""))
		self.assertEqual(job_id("1000123", "0010"), "1000123|0010")
		self.assertEqual(job_id("1000123"), "1000123")
		for bad in ("", "|0010", "a|b|c", None):
			with self.assertRaises(ValueError, msg=bad):
				parse_job(bad)

	def test_job_without_an_order_mapping_is_the_tag_itself(self):
		fake = FakeInsightsHub()
		resolved = adapter(fake).resolve("Job Card", "1000123|0010")
		self.assertEqual((resolved.external_id, resolved.label), ("1000123|0010", "1000123 0010"))
		self.assertEqual(resolved.data, {"order": "1000123", "operation": "0010", "checked": False})
		self.assertEqual(fake.requests, [])
		self.assertEqual(adapter(fake).resolve("Job Card", "1000123").label, "1000123")
		self.assertIsNone(adapter(fake).resolve("Job Card", "a|b|c"))

	def test_job_is_checked_against_a_mapped_order(self):
		order = {"orderNumber": "1000123", "material": {"description": "Foam block"}}
		fake = FakeInsightsHub().on("GET", "/orders", page([order], "orders"))
		resolved = adapter(fake, overrides={"Work Order": ORDERS}).resolve("Job Card", "1000123|0010")
		self.assertEqual((resolved.external_id, resolved.label), ("1000123|0010", "1000123 0010: Foam block"))
		self.assertEqual(resolved.data["checked"], True)
		self.assertEqual(resolved.data["order_label"], "Foam block")
		self.assertEqual(requests_of(fake, "GET")[0]["query"]["filter"], {"orderNumber": "1000123"})
		missing = FakeInsightsHub().on("GET", "/orders", page([], "orders"))
		self.assertIsNone(adapter(missing, overrides={"Work Order": ORDERS}).resolve("Job Card", "9|0010"))
		down = FakeInsightsHub().on("GET", "/orders", hub_error(503, "C", "down"))
		with self.assertRaises(AdapterUnavailable):
			adapter(down, overrides={"Work Order": ORDERS}).resolve("Job Card", "9|0010")

	def test_mapped_job_card_uses_the_mapping(self):
		jobs = {"service": "oi/v1", "resource": "jobs", "key_fields": "jobId"}
		fake = FakeInsightsHub().on("GET", "/jobs/J1", ok({"jobId": "J1"}))
		resolved = adapter(fake, overrides={"Job Card": jobs}).resolve("Job Card", "J1")
		self.assertEqual(resolved.external_id, "J1")
		self.assertEqual(requests_of(fake, "GET")[0]["path"], "/api/oi/v1/jobs/J1")


if __name__ == "__main__":
	unittest.main()
