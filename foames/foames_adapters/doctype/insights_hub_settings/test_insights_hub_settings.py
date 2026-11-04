# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe

from foames.foames_adapters import get_adapter, get_available_erp_systems
from foames.foames_adapters.insights_hub import ADAPTER_KEY
from foames.foames_adapters.insights_hub.fake import FakeInsightsHub, ok, page
from foames.foames_adapters.insights_hub.rest import SERVICE_CREDENTIALS, TOKEN_MANAGER
from foames.tests_compat import IntegrationTestCase


class TestInsightsHubSettings(IntegrationTestCase):
	def settings(self, **values):
		doc = frappe.get_single("Insights Hub Settings")
		doc.update(
			{
				"enabled": 1,
				"gateway_url": "https://gateway.eu1.example",
				"tenant": "plant1",
				"auth_method": TOKEN_MANAGER,
				"client_id": "c",
				"client_secret": "s",
				"app_name": "foames",
				"entity_mappings": [],
				**values,
			}
		)
		return doc

	def test_registered_and_available_when_enabled(self):
		self.settings().save()
		systems = {row["key"]: row for row in get_available_erp_systems()}
		self.assertEqual(systems[ADAPTER_KEY]["label"], "Siemens Insights Hub")
		self.assertTrue(systems[ADAPTER_KEY]["available"])
		self.settings(enabled=0).save()
		self.assertFalse(get_adapter(ADAPTER_KEY).is_available())

	def test_token_manager_needs_an_app_name(self):
		with self.assertRaises(frappe.ValidationError):
			self.settings(app_name="").save()

	def test_service_credentials_need_a_token_url(self):
		with self.assertRaises(frappe.ValidationError):
			self.settings(auth_method=SERVICE_CREDENTIALS, token_url="").save()
		self.settings(
			auth_method=SERVICE_CREDENTIALS, token_url="https://plant1.piam.eu1.example/oauth/token"
		).save()

	def test_mapping_rows_are_checked(self):
		doc = self.settings()
		doc.append(
			"entity_mappings",
			{"reference_type": "Item", "service": "oi/v1", "resource": "materials", "key_fields": "id"},
		)
		doc.append(
			"entity_mappings",
			{"reference_type": "Item", "service": "oi/v1", "resource": "materials", "key_fields": "id"},
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc = self.settings()
		doc.append(
			"entity_mappings",
			{
				"reference_type": "Batch",
				"service": "oi/v1",
				"resource": "batches",
				"key_fields": "a,b",
				"lookup": "Path",
			},
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_rollup_needs_distinct_variables(self):
		with self.assertRaises(frappe.ValidationError):
			self.settings(send_machine_data=1, good_variable="count", scrap_variable="count").save()
		doc = self.settings(
			send_machine_data=1, property_set="Prod", good_variable="ok", scrap_variable="nok"
		)
		doc.save()
		options = doc.rollup_options()
		self.assertEqual(
			(options.property_set, options.variable("good"), options.variable("run_minutes")),
			("Prod", "ok", "runMinutes"),
		)

	def test_connection_reads_the_password_field(self):
		doc = self.settings()
		doc.save()
		connection = frappe.get_single("Insights Hub Settings").connection()
		self.assertEqual(
			(connection.client_id, connection.client_secret, connection.app_name), ("c", "s", "foames")
		)
		self.assertEqual(connection.host_tenant, "")

	def test_external_reference_resolves_an_asset(self):
		self.settings().save()
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		reference = frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": ADAPTER_KEY,
				"reference_type": "Workstation",
				"external_id": "a1",
			}
		).insert()
		fake = FakeInsightsHub().on("GET", "/assets/a1", ok({"assetId": "a1", "name": "Press 1"}))
		adapter = get_adapter(ADAPTER_KEY)
		adapter._transport = fake
		resolved = adapter.resolve("Workstation", reference.external_id)
		self.assertEqual(resolved.label, "Press 1")
		self.assertEqual(fake.requests[-1]["path"], "/api/assetmanagement/v3/assets/a1")

	def test_connection_test_reads_one_asset(self):
		doc = self.settings()
		doc.save()
		fake = FakeInsightsHub().on("GET", "/assets", page([{"assetId": "a1"}]))
		client = doc.client(transport=fake)
		rows = client.get_page("assetmanagement/v3/assets", size=1)
		self.assertEqual(rows, [{"assetId": "a1"}])
		self.assertEqual(fake.requests[-1]["query"]["size"], "1")
