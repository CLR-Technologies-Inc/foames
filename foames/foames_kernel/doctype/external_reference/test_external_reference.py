# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe

from foames.foames_adapters.test_adapters import FakeAdapter
from foames.foames_kernel.doctype.external_reference import external_reference
from foames.foames_kernel.doctype.external_reference.external_reference import get_reference
from foames.tests_compat import IntegrationTestCase


class TestExternalReference(IntegrationTestCase):
	def setUp(self):
		self.adapter = FakeAdapter(records={"I-1": "Widget"})
		patcher = patch.object(external_reference, "get_adapters", return_value={"Fake": self.adapter})
		patcher.start()
		self.addCleanup(patcher.stop)
		patcher = patch.object(external_reference, "get_adapter", return_value=self.adapter)
		patcher.start()
		self.addCleanup(patcher.stop)

	def make(self, external_id="I-1", erp_system="Fake", reference_type="Item"):
		return frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": erp_system,
				"reference_type": reference_type,
				"external_id": external_id,
			}
		)

	def test_resolves_on_save(self):
		doc = self.make().insert()
		self.assertEqual(doc.status, "Resolved")
		self.assertEqual(doc.label, "Widget")
		self.assertTrue(doc.last_resolved_on)

	def test_missing_record_is_marked_missing(self):
		doc = self.make("I-404").insert()
		self.assertEqual(doc.status, "Missing")

	def test_missing_clears_previous_label(self):
		doc = self.make().insert()
		del self.adapter.records["I-1"]
		doc.save()
		self.assertEqual(doc.status, "Missing")
		self.assertIsNone(doc.label)

	def test_resolve_action_looks_up_once(self):
		doc = self.make().insert()
		self.adapter.fetch_count = 0
		doc.resolve()
		self.assertEqual(self.adapter.fetch_count, 1)
		self.assertEqual(doc.status, "Resolved")

	def test_stays_unverified_when_erp_unavailable(self):
		self.adapter.available = False
		doc = self.make().insert()
		self.assertEqual(doc.status, "Unverified")

	def test_rejects_unregistered_erp(self):
		with self.assertRaises(frappe.ValidationError):
			self.make(erp_system="Unknown").insert()

	def test_rejects_unsupported_reference_type(self):
		with self.assertRaises(frappe.ValidationError):
			self.make(reference_type="Batch").insert()

	def test_rejects_duplicates(self):
		self.make().insert()
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make().insert()

	def test_get_reference_reuses_existing(self):
		first = get_reference("Fake", "Item", "I-1")
		self.assertEqual(get_reference("Fake", "Item", "I-1"), first)
