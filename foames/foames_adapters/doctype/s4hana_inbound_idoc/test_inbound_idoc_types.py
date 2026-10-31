# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Inbound IDocs of every kind FoaMES knows, the handler hook, and the HTTP endpoint S/4HANA posts to."""

import json

import frappe

from foames.foames_adapters.doctype.s4hana_inbound_idoc.s4hana_inbound_idoc import receive
from foames.foames_adapters.s4hana import idoc
from foames.foames_adapters.s4hana.api import receive_idoc
from foames.foames_adapters.s4hana.test_idoc import BATMAS, MATMAS
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, extra_hooks, fake_request, make_user

UNKNOWN = b"""<ZFOAM01>
 <IDOC BEGIN="1">
  <EDI_DC40 SEGMENT="1"><DOCNUM>9001</DOCNUM><MESTYP>ZFOAM</MESTYP><SNDPRN>S4H</SNDPRN></EDI_DC40>
  <Z1FOAM SEGMENT="1"><FIELD>value</FIELD></Z1FOAM>
 </IDOC>
</ZFOAM01>"""

HANDLED = []


def remember(doc, parsed, summary):
	HANDLED.append((doc.name, parsed.message_type, summary.get("external_id")))


def explode(doc, parsed, summary):
	raise RuntimeError("handler exploded")


class TestInboundIDocTypes(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		HANDLED.clear()
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		frappe.db.delete("S4HANA Inbound IDoc")

	def reference_of(self, name):
		return frappe.get_doc(
			"External Reference", frappe.db.get_value("S4HANA Inbound IDoc", name, "external_reference")
		)

	def test_material_master_records_an_item_reference(self):
		[parsed] = idoc.parse(MATMAS)
		name, new = receive(parsed)
		self.assertTrue(new)
		doc = frappe.get_doc("S4HANA Inbound IDoc", name)
		self.assertEqual(
			(doc.status, doc.message_type, doc.idoc_type, doc.sender),
			("Processed", "MATMAS", "MATMAS05", "S4HCLNT100"),
		)
		# The IDoc number is kept without its leading zeros.
		self.assertEqual((doc.name, doc.idoc_number), ("S4HCLNT100-777", "777"))
		reference = self.reference_of(name)
		self.assertEqual(
			(reference.erp_system, reference.reference_type, reference.external_id),
			("S4HANA", "Item", "FG-1"),
		)
		summary = json.loads(doc.summary)
		self.assertEqual((summary["base_unit"], summary["description"]), ("KG", "Foam"))
		self.assertIn("E1MARAM", json.loads(doc.segments))

	def test_batch_master_records_a_batch_reference(self):
		[parsed] = idoc.parse(BATMAS % b"1010")
		name, _ = receive(parsed)
		reference = self.reference_of(name)
		self.assertEqual((reference.reference_type, reference.external_id), ("Batch", "FG-1|1010|B001"))

	def test_unknown_message_type_is_kept_without_a_reference(self):
		[parsed] = idoc.parse(UNKNOWN)
		name, new = receive(parsed)
		doc = frappe.get_doc("S4HANA Inbound IDoc", name)
		self.assertEqual((new, doc.status, doc.message_type), (True, "Processed", "ZFOAM"))
		self.assertIsNone(doc.external_reference)
		self.assertIsNone(doc.summary)
		self.assertEqual(json.loads(doc.segments)["Z1FOAM"][0]["FIELD"], "value")

	def test_handlers_run_for_their_message_type_only(self):
		path = "foames.foames_adapters.doctype.s4hana_inbound_idoc.test_inbound_idoc_types.remember"
		with extra_hooks(foames_s4hana_idoc_handlers={"MATMAS": [path]}):
			name, _ = receive(idoc.parse(MATMAS)[0])
			receive(idoc.parse(BATMAS % b"")[0])
		self.assertEqual(HANDLED, [(name, "MATMAS", "FG-1")])

	def test_failing_handler_marks_the_idoc_failed_and_keeps_it(self):
		path = "foames.foames_adapters.doctype.s4hana_inbound_idoc.test_inbound_idoc_types.explode"
		with extra_hooks(foames_s4hana_idoc_handlers={"MATMAS": [path]}):
			name, new = receive(idoc.parse(MATMAS)[0])
		doc = frappe.get_doc("S4HANA Inbound IDoc", name)
		self.assertEqual((new, doc.status), (True, "Failed"))
		self.assertIn("handler exploded", doc.error)
		self.assertIsNone(doc.external_reference)
		self.assertFalse(
			frappe.db.exists("External Reference", {"erp_system": "S4HANA", "external_id": "FG-1"})
		)
		# The resend is still recognised, so S/4HANA's retry does not run the handler again.
		self.assertEqual(receive(idoc.parse(MATMAS)[0]), (name, False))

	def test_two_idocs_in_one_file(self):
		combined = BATMAS % b"1010"
		combined = combined.replace(
			b"</IDOC>\n</BATMAS03>",
			b'</IDOC>\n <IDOC BEGIN="1"><EDI_DC40 SEGMENT="1"><DOCNUM>43</DOCNUM><MESTYP>BATMAS</MESTYP><SNDPRN>S4H</SNDPRN></EDI_DC40><E1BATMAS SEGMENT="1"><MATERIAL>FG-2</MATERIAL><BATCH>B002</BATCH></E1BATMAS></IDOC>\n</BATMAS03>',
		)
		parsed = idoc.parse(combined)
		self.assertEqual([p.number for p in parsed], ["42", "43"])
		names = [receive(p)[0] for p in parsed]
		self.assertEqual(names, ["S4H-42", "S4H-43"])
		self.assertEqual(self.reference_of("S4H-43").external_id, "FG-2|B002")


class TestReceiveIDocEndpoint(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		frappe.db.set_single_value("S4HANA Settings", "enabled", 1)
		frappe.db.delete("S4HANA Inbound IDoc")
		make_user("foames-idoc-integration@example.com", "FoaMES Integration")
		make_user("foames-idoc-nobody@example.com")

	def post(self, body, user="foames-idoc-integration@example.com"):
		with as_user(user), fake_request(body, {"Content-Type": "application/xml"}):
			return receive_idoc()

	def test_integration_user_posts_idocs(self):
		result = self.post(MATMAS)
		self.assertEqual(result, {"received": ["S4HCLNT100-777"], "duplicates": []})
		result = self.post(MATMAS)
		self.assertEqual(result, {"received": [], "duplicates": ["S4HCLNT100-777"]})
		doc = frappe.get_doc("S4HANA Inbound IDoc", "S4HCLNT100-777")
		self.assertEqual(doc.status, "Processed")
		self.assertTrue(doc.external_reference)

	def test_needs_the_integration_role(self):
		with self.assertRaises(frappe.PermissionError):
			self.post(MATMAS, user="foames-idoc-nobody@example.com")

	def test_disabled_adapter_refuses(self):
		frappe.db.set_single_value("S4HANA Settings", "enabled", 0)
		with self.assertRaises(frappe.ValidationError):
			self.post(MATMAS)
		self.assertEqual(frappe.db.count("S4HANA Inbound IDoc"), 0)

	def test_bad_xml_is_a_validation_error(self):
		with self.assertRaises(frappe.ValidationError):
			self.post(b"<not an idoc>")
		with self.assertRaises(frappe.ValidationError):
			self.post(b"<X><IDOC><E1MARAM/></IDOC></X>")
