# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import unittest

import frappe

from foames.foames_adapters import (
	REFERENCE_TYPES,
	AdapterError,
	AdapterUnavailable,
	ERPAdapter,
	ResolvedReference,
	UnsupportedReferenceType,
	get_adapter,
	get_adapters,
	get_available_erp_systems,
)
from foames.foames_adapters.erpnext import ERPNEXT_DOCTYPES, ERPNextAdapter
from foames.tests_compat import IntegrationTestCase


class FakeAdapter(ERPAdapter):
	key = "Fake"
	label = "Fake ERP"
	reference_map = {"Item": "Fake Item"}  # noqa: RUF012

	def __init__(self, available=True, records=None):
		self.available = available
		self.records = records or {}
		self.fetch_count = 0

	def is_available(self):
		return self.available

	def fetch(self, erp_type, reference_type, external_id):
		self.fetch_count += 1
		label = self.records.get(external_id)
		if label is None:
			return None
		return ResolvedReference(reference_type, external_id, label, {"type": erp_type})


class TestAdapterContract(unittest.TestCase):
	def test_resolves_supported_type(self):
		resolved = FakeAdapter(records={"I-1": "Widget"}).resolve("Item", "I-1")
		self.assertEqual(resolved.label, "Widget")
		self.assertEqual(resolved.data, {"type": "Fake Item"})

	def test_missing_record_returns_none(self):
		self.assertIsNone(FakeAdapter().resolve("Item", "nope"))

	def test_unsupported_type_raises(self):
		with self.assertRaises(UnsupportedReferenceType):
			FakeAdapter().resolve("Batch", "B-1")

	def test_unavailable_adapter_raises(self):
		with self.assertRaises(AdapterUnavailable):
			FakeAdapter(available=False).resolve("Item", "I-1")

	def test_erpnext_adapter_covers_every_kernel_type(self):
		self.assertEqual(set(ERPNEXT_DOCTYPES), set(REFERENCE_TYPES))
		for reference_type in REFERENCE_TYPES:
			self.assertTrue(ERPNextAdapter().supports(reference_type))


class TestAdapterRegistry(IntegrationTestCase):
	def test_erpnext_adapter_is_registered(self):
		self.assertIsInstance(get_adapters()["ERPNext"], ERPNextAdapter)

	def test_unknown_adapter_raises(self):
		with self.assertRaises(AdapterError):
			get_adapter("Not An ERP")

	def test_availability_follows_installed_apps(self):
		installed = "erpnext" in frappe.get_installed_apps()
		systems = {row["key"]: row for row in get_available_erp_systems()}
		self.assertEqual(systems["ERPNext"]["available"], installed)


class TestERPNextAdapter(IntegrationTestCase):
	def setUp(self):
		if "erpnext" not in frappe.get_installed_apps():
			self.skipTest("ERPNext is not installed on this site")

	def test_resolves_unit_of_measure(self):
		# A fresh site has no UOMs until the setup wizard runs, so create one.
		uom = "FoaMES Test Unit"
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert()
		self.addCleanup(frappe.db.rollback)
		resolved = get_adapter("ERPNext").resolve("Unit of Measure", uom)
		self.assertEqual(resolved.external_id, uom)
		self.assertEqual(resolved.data["doctype"], "UOM")

	def test_missing_record_returns_none(self):
		self.assertIsNone(get_adapter("ERPNext").resolve("Item", "foames-test-no-such-item"))
