# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe

from foames.foames_adapters import get_adapters
from foames.foames_adapters.s4hana.adapter import S4HANAAdapter
from foames.tests_compat import IntegrationTestCase


class TestS4HANASettings(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def test_adapter_is_registered(self):
		self.assertIsInstance(get_adapters()["S4HANA"], S4HANAAdapter)

	def test_mapping_adds_reference_type(self):
		settings = frappe.get_single("S4HANA Settings")
		settings.set("entity_mappings", [])
		settings.append(
			"entity_mappings",
			{
				"reference_type": "Location",
				"service": "API_PLANT_SRV",
				"entity_set": "A_Plant",
				"key_fields": "Plant",
			},
		)
		settings.save()
		self.assertTrue(get_adapters()["S4HANA"].supports("Location"))

	def test_duplicate_mapping_rejected(self):
		settings = frappe.get_single("S4HANA Settings")
		settings.set("entity_mappings", [])
		row = {"reference_type": "Item", "service": "S", "entity_set": "E", "key_fields": "K"}
		settings.append("entity_mappings", row)
		settings.append("entity_mappings", row)
		with self.assertRaises(frappe.ValidationError):
			settings.save()
