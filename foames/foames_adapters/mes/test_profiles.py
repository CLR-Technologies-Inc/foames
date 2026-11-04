# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Every vendor profile and its adapter class, against the scripted fake: the profiles are consistent
with the kernel, each adapter follows the contract, and the lookups a profile ships send the documented
request. No Frappe site needed."""

import unittest
from types import SimpleNamespace

from foames.foames_adapters.aegis_factorylogix.adapter import AegisFactoryLogixAdapter
from foames.foames_adapters.aveva_mes.adapter import AvevaMESAdapter
from foames.foames_adapters.base import (
	REFERENCE_TYPES,
	AdapterError,
	AdapterUnavailable,
	UnsupportedReferenceType,
)
from foames.foames_adapters.critical_manufacturing.adapter import CriticalManufacturingAdapter
from foames.foames_adapters.delmia_apriso.adapter import DelmiaAprisoAdapter
from foames.foames_adapters.factorytalk_productioncentre.adapter import FactoryTalkProductionCentreAdapter
from foames.foames_adapters.koerber_pasx.adapter import KoerberPASXAdapter
from foames.foames_adapters.mes.entities import LOOKUPS
from foames.foames_adapters.mes.fake import FakeMES, mes_error, ok
from foames.foames_adapters.mes.profile import GENERIC_REQUEST, IDEMPOTENCY_KINDS, Profile
from foames.foames_adapters.mes.rest import AUTH_API_KEY, AUTH_OAUTH, Connection, RestClient
from foames.foames_adapters.plex.adapter import PlexAdapter
from foames.foames_adapters.proficy.adapter import ProficyAdapter
from foames.foames_adapters.sap_dmc.adapter import SAPDigitalManufacturingAdapter
from foames.foames_adapters.tulip.adapter import TulipAdapter

ADAPTERS = (
	PlexAdapter,
	FactoryTalkProductionCentreAdapter,
	SAPDigitalManufacturingAdapter,
	DelmiaAprisoAdapter,
	AvevaMESAdapter,
	CriticalManufacturingAdapter,
	TulipAdapter,
	AegisFactoryLogixAdapter,
	KoerberPASXAdapter,
	ProficyAdapter,
)


class FakeConnection(SimpleNamespace):
	"""Stands in for MES Connection: the fields and methods the adapter uses."""

	def client(self, transport=None):
		return RestClient(
			Connection(
				base_url=self.base_url,
				auth=self.auth,
				api_key="k",
				api_key_header=self.profile.api_key_header,
				site=self.site,
				headers=dict(self.profile.headers),
				token_url="https://auth.example/oauth/token",
			),
			transport=transport,
		)


def adapter(cls, fake=None, enabled=1, base_url="https://mes.example/api", site="1010", mappings=None):
	connection = FakeConnection(
		enabled=enabled, base_url=base_url, site=site, auth=cls.profile.default_auth, profile=cls.profile
	)
	connection.entity_mappings = mappings or []
	return cls(connection, transport=fake or FakeMES())


class TestProfiles(unittest.TestCase):
	def test_every_profile_is_consistent(self):
		keys, labels = set(), set()
		for cls in ADAPTERS:
			profile = cls.profile
			self.assertIsInstance(profile, Profile)
			self.assertNotIn(profile.key, keys)
			self.assertNotIn(profile.label, labels)
			keys.add(profile.key)
			labels.add(profile.label)
			self.assertRegex(profile.key, r"^[A-Z][A-Z0-9_]+$")
			self.assertTrue(profile.docs_url.startswith("https://"))
			self.assertTrue(profile.base_url_hint.startswith("https://"))
			self.assertTrue(profile.vendor and profile.product and profile.notes)
			self.assertIn(GENERIC_REQUEST, profile.operations)
			for operation in profile.operations.values():
				self.assertIn(operation.idempotency, IDEMPOTENCY_KINDS)
			for reference_type, spec in profile.entities.items():
				self.assertIn(reference_type, REFERENCE_TYPES)
				self.assertIn(spec.lookup, LOOKUPS)
				self.assertTrue(spec.key_fields)
			if AUTH_API_KEY in profile.auth_methods:
				self.assertTrue(profile.api_key_header)
			if AUTH_OAUTH in profile.auth_methods:
				self.assertTrue(profile.token_url_hint or profile.docs_url)
			if "{site}" in str(profile.headers) or any(
				"{site}" in str(s.extra_query) for s in profile.entities.values()
			):
				self.assertTrue(profile.site_label, msg=profile.key)

	def test_profile_validation(self):
		with self.assertRaises(ValueError):
			Profile(
				key="",
				label="x",
				vendor="v",
				product="p",
				docs_url="https://d",
				base_url_hint="https://b",
				auth_methods=("Basic",),
			)
		with self.assertRaises(ValueError):
			Profile(
				key="X",
				label="x",
				vendor="v",
				product="p",
				docs_url="https://d",
				base_url_hint="https://b",
				auth_methods=("Magic",),
			)
		with self.assertRaises(ValueError):
			Profile(
				key="X",
				label="x",
				vendor="v",
				product="p",
				docs_url="https://d",
				base_url_hint="https://b",
				auth_methods=(),
			)

	def test_adapter_contract(self):
		for cls in ADAPTERS:
			a = adapter(cls)
			self.assertEqual((a.key, a.label), (cls.profile.key, cls.profile.label))
			self.assertTrue(a.is_available())
			self.assertFalse(adapter(cls, enabled=0).is_available())
			self.assertFalse(adapter(cls, base_url="").is_available())
			for reference_type in cls.profile.entities:
				self.assertTrue(a.supports(reference_type))

	def test_unavailable_without_a_connection_record(self):
		class Disconnected(PlexAdapter):
			@property
			def connection(self):
				return None

		self.assertFalse(Disconnected().is_available())
		self.assertEqual(Disconnected().reference_map, {})


class TestMappedLookups(unittest.TestCase):
	def test_unmapped_type_is_refused_before_any_request(self):
		fake = FakeMES()
		with self.assertRaises(UnsupportedReferenceType):
			adapter(PlexAdapter, fake).resolve("Item", "P1")
		self.assertEqual(fake.requests, [])

	def test_plex_mapping_sends_the_api_key_and_customer_headers(self):
		mapping = {
			"reference_type": "Item",
			"path": "mdm/v1/parts",
			"lookup": "Query",
			"key_fields": "number",
			"label_field": "name",
		}
		fake = FakeMES().on("GET", "/mdm/v1/parts", ok([{"number": "P1", "name": "Bracket"}]))
		resolved = adapter(PlexAdapter, fake, site="PCN-7", mappings=[mapping]).resolve("Item", "P1")
		self.assertEqual((resolved.external_id, resolved.label), ("P1", "Bracket"))
		request = fake.requests[-1]
		self.assertEqual(request["query"], {"number": "P1"})
		self.assertEqual(request["headers"]["X-Plex-Connect-Api-Key"], "k")
		self.assertEqual(request["headers"]["X-Plex-Connect-Customer-Id"], "PCN-7")
		self.assertEqual(resolved.data, {"path": "mdm/v1/parts", "lookup": "Query", "keys": {"number": "P1"}})

	def test_path_lookup_and_missing_record(self):
		mapping = {
			"reference_type": "Workstation",
			"path": "machines/{id}",
			"lookup": "Path",
			"key_fields": "id",
			"label_field": "name",
		}
		fake = FakeMES().on("GET", "/machines/m1", ok({"id": "m1", "name": "Press"}))
		a = adapter(TulipAdapter, fake, mappings=[mapping])
		self.assertEqual(a.resolve("Workstation", "m1").label, "Press")
		self.assertIsNone(a.resolve("Workstation", "m2"))
		empty = FakeMES().on("GET", "/machines/m3", ok({}))
		self.assertIsNone(adapter(TulipAdapter, empty, mappings=[mapping]).resolve("Workstation", "m3"))

	def test_status_mapping(self):
		mapping = {"reference_type": "Item", "path": "items", "lookup": "Query", "key_fields": "id"}
		for status, expected in (
			(401, AdapterUnavailable),
			(429, AdapterUnavailable),
			(503, AdapterUnavailable),
			(400, AdapterError),
			(409, AdapterError),
		):
			fake = FakeMES().on("GET", "/items", mes_error(status, f"status {status}"))
			with self.assertRaises(expected, msg=status) as raised:
				adapter(AvevaMESAdapter, fake, mappings=[mapping]).resolve("Item", "I1")
			self.assertIn("AVEVA", str(raised.exception))
		for error in (TimeoutError(), OSError("dns")):
			with self.assertRaises(AdapterUnavailable):
				adapter(AvevaMESAdapter, FakeMES().on("GET", "/items", error), mappings=[mapping]).resolve(
					"Item", "I1"
				)

	def test_bad_external_id_is_missing_without_a_request(self):
		mapping = {
			"reference_type": "Batch",
			"path": "batches",
			"lookup": "Query",
			"key_fields": "material,batch",
		}
		fake = FakeMES()
		self.assertIsNone(adapter(KoerberPASXAdapter, fake, mappings=[mapping]).resolve("Batch", "B7"))
		self.assertEqual(fake.requests, [])


class TestSAPDigitalManufacturing(unittest.TestCase):
	def test_defaults_cover_the_execution_model(self):
		self.assertEqual(
			set(SAPDigitalManufacturingAdapter.profile.entities),
			{"Item", "Work Order", "Workstation", "Location", "Job Card"},
		)
		self.assertEqual(SAPDigitalManufacturingAdapter.profile.auth_methods, (AUTH_OAUTH,))

	def test_order_lookup_carries_the_plant(self):
		order = {
			"order": "1000123",
			"status": "ACTIVE",
			"material": {"material": "FG-1", "description": "Foam block"},
		}
		fake = FakeMES().on("GET", "/order/v1/orders", ok(order))
		resolved = adapter(SAPDigitalManufacturingAdapter, fake, site="1010").resolve("Work Order", "1000123")
		self.assertEqual((resolved.external_id, resolved.label), ("1000123", "Foam block"))
		request = fake.requests[-1]
		self.assertEqual(request["path"], "/api/order/v1/orders")
		self.assertEqual(request["query"], {"plant": "1010", "order": "1000123"})
		self.assertEqual(request["headers"]["Authorization"], "Bearer T1")

	def test_sfc_is_the_job_card(self):
		fake = FakeMES().on("GET", "/sfc/v1/sfcdetail", ok({"sfc": "S1", "order": "1000123"}))
		resolved = adapter(SAPDigitalManufacturingAdapter, fake).resolve("Job Card", "S1")
		self.assertEqual((resolved.external_id, resolved.label), ("S1", "1000123"))

	def test_mapping_overrides_a_default(self):
		mapping = {
			"reference_type": "Item",
			"path": "material/v2/materials",
			"lookup": "Query",
			"key_fields": "material",
			"extra_query": "plant={site}",
		}
		fake = FakeMES().on("GET", "/material/v2/materials", ok([{"material": "FG-1"}]))
		adapter(SAPDigitalManufacturingAdapter, fake, mappings=[mapping]).resolve("Item", "FG-1")
		self.assertEqual(fake.requests[-1]["path"], "/api/material/v2/materials")

	def test_empty_collection_is_missing(self):
		fake = FakeMES().on("GET", "/material/v1/materials", ok({"content": []}))
		self.assertIsNone(adapter(SAPDigitalManufacturingAdapter, fake).resolve("Item", "FG-9"))


if __name__ == "__main__":
	unittest.main()
