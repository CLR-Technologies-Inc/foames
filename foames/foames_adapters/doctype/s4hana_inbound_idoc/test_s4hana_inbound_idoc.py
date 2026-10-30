# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json

import frappe

from foames.foames_adapters.doctype.s4hana_inbound_idoc.s4hana_inbound_idoc import receive
from foames.foames_adapters.s4hana import idoc
from foames.foames_adapters.s4hana.test_s4hana import LOIPRO
from foames.tests_compat import IntegrationTestCase


class TestS4HANAInboundIDoc(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		frappe.db.delete("S4HANA Inbound IDoc")
		self.addCleanup(frappe.db.rollback)

	def test_order_download_records_work_order_reference(self):
		[parsed] = idoc.parse(LOIPRO)
		name, new = receive(parsed)
		self.assertTrue(new)
		doc = frappe.get_doc("S4HANA Inbound IDoc", name)
		self.assertEqual((doc.status, doc.message_type, doc.idoc_number), ("Processed", "LOIPRO", "123456"))
		reference = frappe.get_doc("External Reference", doc.external_reference)
		self.assertEqual(
			(reference.erp_system, reference.reference_type, reference.external_id),
			("S4HANA", "Work Order", "1000123"),
		)
		self.assertEqual(json.loads(doc.summary)["plant"], "1010")

	def test_resend_is_not_processed_twice(self):
		[parsed] = idoc.parse(LOIPRO)
		first, _ = receive(parsed)
		second, new = receive(parsed)
		self.assertEqual((second, new), (first, False))
		self.assertEqual(frappe.db.count("S4HANA Inbound IDoc"), 1)
