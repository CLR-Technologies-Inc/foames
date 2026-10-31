# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe

from foames.foames_adapters.doctype.s4hana_settings.s4hana_settings import S4HANASettings
from foames.foames_adapters.s4hana.entities import DEFAULT_ENTITIES
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, sap_error
from foames.foames_adapters.s4hana.odata import ODataClient
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_user


class TestS4HANASettingsConnection(IntegrationTestCase):
	def settings(self, **values):
		settings = frappe.get_single("S4HANA Settings")
		settings.update(
			{
				"base_url": "https://s4.example.com:44300/",
				"sap_client": "100",
				"auth_method": "Basic",
				"username": "FOAMES_COMM",
				"password": "secret",
				"token_url": None,
				"client_id": None,
				"client_secret": None,
				"scope": None,
				"language": None,
				"timeout": 0,
				"ca_bundle": None,
			}
		)
		settings.update(values)
		settings.save()
		return settings

	def test_connection_carries_every_field(self):
		settings = self.settings(language="DE", timeout=12, ca_bundle="/etc/ssl/sap.pem")
		connection = settings.connection()
		self.assertEqual(
			(connection.base_url, connection.client, connection.auth),
			("https://s4.example.com:44300/", "100", "Basic"),
		)
		self.assertEqual((connection.username, connection.password), ("FOAMES_COMM", "secret"))
		self.assertEqual(
			(connection.language, connection.timeout, connection.cafile), ("DE", 12.0, "/etc/ssl/sap.pem")
		)

	def test_defaults_when_fields_are_empty(self):
		connection = self.settings().connection()
		self.assertEqual((connection.language, connection.timeout, connection.cafile), ("EN", 30.0, None))
		self.assertEqual(
			(connection.token_url, connection.client_id, connection.client_secret, connection.scope),
			("", "", "", ""),
		)

	def test_oauth_secrets_are_decrypted(self):
		settings = self.settings(
			auth_method="OAuth 2.0 Client Credentials",
			token_url="https://auth.example.com/oauth/token",
			client_id="foames",
			client_secret="very-secret",
			scope="API_PRODUCT_SRV_0001",
		)
		connection = settings.connection()
		self.assertEqual(
			(connection.client_id, connection.client_secret, connection.scope),
			("foames", "very-secret", "API_PRODUCT_SRV_0001"),
		)
		self.assertNotEqual(frappe.db.get_single_value("S4HANA Settings", "client_secret"), "very-secret")

	def test_entity_specs_merge_overrides_with_defaults(self):
		settings = self.settings()
		settings.set("entity_mappings", [])
		settings.append(
			"entity_mappings",
			{
				"reference_type": "Item",
				"service": "ZAPI_PRODUCT_SRV",
				"entity_set": "Z_Product",
				"key_fields": "Product, Plant",
				"optional_keys": "Plant",
				"label_field": "ProductName",
			},
		)
		settings.save()
		specs = settings.entity_specs()
		self.assertEqual(set(specs) >= set(DEFAULT_ENTITIES), True)
		item = specs["Item"]
		self.assertEqual(
			(item.service, item.entity_set, item.key_fields),
			("ZAPI_PRODUCT_SRV", "Z_Product", ("Product", "Plant")),
		)
		self.assertEqual(item.key_defaults, {"Plant": ""})
		self.assertEqual(specs["Batch"], DEFAULT_ENTITIES["Batch"])

	def test_incomplete_mapping_row_is_refused(self):
		settings = self.settings()
		settings.set("entity_mappings", [])
		settings.append(
			"entity_mappings",
			{"reference_type": "Location", "service": "API_PLANT_SRV", "entity_set": "A_Plant"},
		)
		with self.assertRaises(frappe.ValidationError):
			settings.save()


class TestConnectionCheck(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.settings = frappe.get_single("S4HANA Settings")
		self.settings.update(
			{
				"base_url": "https://s4.example.com",
				"sap_client": "100",
				"auth_method": "Basic",
				"username": "u",
				"password": "p",
			}
		)
		self.settings.save()

	def client_with(self, fake):
		return patch.object(
			S4HANASettings, "client", lambda s, transport=None: ODataClient(s.connection(), transport=fake)
		)

	def test_fetches_a_csrf_token_from_the_product_service(self):
		fake = FakeS4HANA().on("FETCH", "API_PRODUCT_SRV", csrf("TOKEN-1"))
		with self.client_with(fake):
			message = self.settings.test_connection()
		self.assertIn("https://s4.example.com", message)
		[request] = fake.requests
		self.assertEqual(request["headers"]["X-CSRF-Token"], "Fetch")
		self.assertIn("API_PRODUCT_SRV", request["path"])
		self.assertEqual(request["query"].get("sap-client"), "100")

	def test_rejection_becomes_a_readable_error(self):
		fake = FakeS4HANA().on("FETCH", "API_PRODUCT_SRV", sap_error(401, "", "Unauthorized"))
		with self.client_with(fake), self.assertRaises(frappe.ValidationError) as caught:
			self.settings.test_connection()
		self.assertIn("401", str(caught.exception))

	def test_only_system_managers_may_test(self):
		make_user("foames-s4-engineer@example.com", "FoaMES Engineer")
		with as_user("foames-s4-engineer@example.com"), self.assertRaises(frappe.PermissionError):
			self.settings.test_connection()
