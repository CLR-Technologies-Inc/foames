# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe

from foames.foames_adapters import get_adapter, get_adapters, get_available_erp_systems
from foames.foames_adapters.doctype.mes_connection.mes_connection import profiles
from foames.foames_adapters.mes.adapter import ProfileAdapter
from foames.foames_adapters.mes.fake import FakeMES, ok
from foames.tests_compat import IntegrationTestCase


class TestMESConnection(IntegrationTestCase):
	def connection(self, adapter="SAP_DMC", **values):
		if frappe.db.exists("MES Connection", adapter):
			doc = frappe.get_doc("MES Connection", adapter)
		else:
			doc = frappe.new_doc("MES Connection")
			doc.adapter = adapter
		doc.update(
			{
				"enabled": 1,
				"base_url": "https://api.eu10.dmc.example",
				"site": "1010",
				"auth_method": "OAuth 2.0 Client Credentials",
				"token_url": "https://sub.authentication.eu10.example/oauth/token",
				"client_id": "c",
				"client_secret": "s",
				"entity_mappings": [],
				**values,
			}
		)
		return doc

	def test_every_profile_adapter_is_registered_and_unavailable_without_a_connection(self):
		registered = {key: a for key, a in get_adapters().items() if isinstance(a, ProfileAdapter)}
		self.assertEqual(set(registered), set(profiles()))
		self.assertGreaterEqual(len(registered), 10)
		systems = {row["key"]: row for row in get_available_erp_systems()}
		for key in registered:
			if not frappe.db.exists("MES Connection", key):
				self.assertFalse(systems[key]["available"], msg=key)

	def test_connection_makes_the_adapter_available(self):
		self.connection().save()
		self.assertTrue(get_adapter("SAP_DMC").is_available())
		doc = self.connection(enabled=0)
		doc.save()
		frappe.clear_document_cache("MES Connection", "SAP_DMC")
		self.assertFalse(get_adapter("SAP_DMC").is_available())

	def test_profile_notes_and_documentation_are_filled(self):
		doc = self.connection()
		doc.save()
		self.assertTrue(doc.profile_notes)
		self.assertTrue(doc.documentation_url.startswith("https://"))

	def test_credentials_are_checked_when_enabled(self):
		with self.assertRaises(frappe.ValidationError):
			self.connection(token_url="").save()
		with self.assertRaises(frappe.ValidationError):
			self.connection("TULIP", auth_method="Basic", username="").save()
		with self.assertRaises(frappe.ValidationError):
			self.connection("PLEX", auth_method="API Key Header", api_key="").save()
		plex = self.connection("PLEX", auth_method="API Key Header", api_key="k", api_key_header="")
		plex.save()
		self.assertEqual(plex.api_key_header, "X-Plex-Connect-Api-Key")

	def test_headers_and_mappings_are_checked(self):
		with self.assertRaises(frappe.ValidationError):
			self.connection(extra_headers="no colon here").save()
		doc = self.connection(extra_headers="X-Api-Version: 2")
		doc.append(
			"entity_mappings",
			{"reference_type": "Batch", "path": "batches", "key_fields": "a,b", "lookup": "Query"},
		)
		doc.append(
			"entity_mappings",
			{"reference_type": "Batch", "path": "batches", "key_fields": "a,b", "lookup": "Query"},
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc = self.connection(extra_headers="X-Api-Version: 2")
		doc.append(
			"entity_mappings",
			{"reference_type": "Batch", "path": "batches", "key_fields": "", "lookup": "Query"},
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_connection_object_reads_passwords_and_profile_headers(self):
		self.connection(
			"PLEX", auth_method="API Key Header", api_key="k", site="PCN-7", extra_headers="X-Api-Version: 2"
		).save()
		connection = frappe.get_doc("MES Connection", "PLEX").connection()
		self.assertEqual(
			(connection.api_key, connection.api_key_header, connection.site),
			("k", "X-Plex-Connect-Api-Key", "PCN-7"),
		)
		self.assertEqual(connection.headers, {"X-Plex-Connect-Customer-Id": "{site}", "X-Api-Version": "2"})

	def test_external_reference_resolves_through_the_connection(self):
		self.connection().save()
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "SAP_DMC",
				"reference_type": "Work Order",
				"external_id": "1000123",
			}
		).insert()
		fake = FakeMES().on(
			"GET", "/order/v1/orders", ok({"order": "1000123", "material": {"description": "Foam"}})
		)
		adapter = get_adapter("SAP_DMC")
		adapter._transport = fake
		resolved = adapter.resolve("Work Order", "1000123")
		self.assertEqual(resolved.label, "Foam")
		self.assertEqual(fake.requests[-1]["query"], {"plant": "1010", "order": "1000123"})

	def test_unmapped_type_cannot_be_referenced(self):
		self.connection("TULIP", auth_method="Basic", username="u", password="p").save()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "External Reference",
					"erp_system": "TULIP",
					"reference_type": "Item",
					"external_id": "P1",
				}
			).insert()
