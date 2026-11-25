# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

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
