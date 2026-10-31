# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The kernel on a site: FoaMES Settings, the adapter registry and External References as other
modules use them."""

import frappe

from foames.foames_adapters import get_adapters, get_available_erp_systems
from foames.foames_kernel.doctype.external_reference.external_reference import (
	get_reference,
	make_reference_key,
)
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_user


class TestFoaMESSettings(IntegrationTestCase):
	def test_default_erp_must_be_a_registered_adapter(self):
		settings = frappe.get_single("FoaMES Settings")
		settings.default_erp_system = "Not An ERP"
		with self.assertRaises(frappe.ValidationError):
			settings.save()
		for key in get_adapters():
			settings.default_erp_system = key
			settings.save()
		settings.default_erp_system = None
		settings.save()

	def test_only_system_managers_read_settings(self):
		make_user("foames-kernel-engineer@example.com", "FoaMES Engineer")
		with as_user("foames-kernel-engineer@example.com"):
			self.assertFalse(frappe.has_permission("FoaMES Settings", "read"))
			self.assertFalse(frappe.has_permission("External Reference", "read"))


class TestAdapterRegistry(IntegrationTestCase):
	def test_both_adapters_are_registered(self):
		systems = {row["key"]: row for row in get_available_erp_systems()}
		self.assertEqual(set(systems) >= {"ERPNext", "S4HANA"}, True)
		self.assertEqual(systems["S4HANA"]["label"], "SAP S/4HANA")

	def test_s4hana_availability_follows_its_settings(self):
		settings = frappe.get_single("S4HANA Settings")
		settings.enabled = 0
		settings.save()
		self.assertFalse(dict((r["key"], r["available"]) for r in get_available_erp_systems())["S4HANA"])
		settings.enabled = 1
		settings.base_url = "https://s4.example.com"
		settings.save()
		self.assertTrue(dict((r["key"], r["available"]) for r in get_available_erp_systems())["S4HANA"])
		settings.enabled = 1
		settings.base_url = None
		settings.save()
		self.assertFalse(dict((r["key"], r["available"]) for r in get_available_erp_systems())["S4HANA"])


class TestExternalReferences(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 0)

	def test_erpnext_reference_resolves_only_where_erpnext_is_installed(self):
		doc = frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "ERPNext",
				"reference_type": "Item",
				"external_id": "T-KERNEL-NO-SUCH-ITEM",
			}
		).insert()
		if "erpnext" in frappe.get_installed_apps():
			self.assertEqual(doc.status, "Missing")
			self.assertTrue(doc.last_resolved_on)
		else:
			self.assertEqual(doc.status, "Unverified")
			self.assertIsNone(doc.last_resolved_on)

	def test_s4hana_reference_stays_unverified_while_the_adapter_is_disabled(self):
		frappe.db.set_single_value("S4HANA Settings", "enabled", 0)
		doc = frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "S4HANA",
				"reference_type": "Work Order",
				"external_id": "1000999",
			}
		).insert()
		self.assertEqual(doc.status, "Unverified")

	def test_reference_key_identifies_the_erp_record(self):
		self.assertEqual(
			make_reference_key("S4HANA", "Item", "FG-1"), make_reference_key("S4HANA", "Item", "FG-1")
		)
		self.assertNotEqual(
			make_reference_key("S4HANA", "Item", "FG-1"), make_reference_key("ERPNext", "Item", "FG-1")
		)
		self.assertNotEqual(
			make_reference_key("S4HANA", "Item", "FG-1"), make_reference_key("S4HANA", "Batch", "FG-1")
		)
		self.assertEqual(len(make_reference_key("S4HANA", "Item", "FG-1")), 64)

	def test_get_reference_respects_permissions_unless_told_otherwise(self):
		frappe.db.set_single_value("S4HANA Settings", "enabled", 0)
		make_user("foames-kernel-integration@example.com", "FoaMES Integration")
		with as_user("foames-kernel-integration@example.com"):
			with self.assertRaises(frappe.PermissionError):
				get_reference("Item", "T-KERNEL-PERM", erp_system="S4HANA")
			name = get_reference("Item", "T-KERNEL-PERM", erp_system="S4HANA", ignore_permissions=True)
			# Once it exists, the lookup needs no permission at all.
			self.assertEqual(get_reference("Item", "T-KERNEL-PERM", erp_system="S4HANA"), name)
		doc = frappe.get_doc("External Reference", name)
		self.assertEqual(
			(doc.erp_system, doc.reference_type, doc.external_id), ("S4HANA", "Item", "T-KERNEL-PERM")
		)

	def test_get_reference_uses_the_default_erp(self):
		frappe.db.set_single_value("FoaMES Settings", "default_erp_system", "S4HANA")
		frappe.db.set_single_value("S4HANA Settings", "enabled", 0)
		name = get_reference("Batch", "FG-1|B001")
		self.assertEqual(frappe.db.get_value("External Reference", name, "erp_system"), "S4HANA")
