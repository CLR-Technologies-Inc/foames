# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""IDoc parsing and summaries for every message type FoaMES knows, and every way a post can be
malformed. No Frappe site needed."""

import unittest

from foames.foames_adapters.s4hana import idoc
from foames.foames_adapters.s4hana.test_s4hana import LOIPRO

MATMAS = b"""<?xml version="1.0" encoding="UTF-8"?>
<MATMAS05>
 <IDOC BEGIN="1">
  <EDI_DC40 SEGMENT="1">
   <DOCNUM>0000000000000777</DOCNUM><IDOCTYP>MATMAS05</IDOCTYP><MESTYP>MATMAS</MESTYP>
   <SNDPRN>S4HCLNT100</SNDPRN><CREDAT>20261030</CREDAT><CRETIM>101500</CRETIM>
   <ZZCUSTOM>ignored</ZZCUSTOM>
  </EDI_DC40>
  <E1MARAM SEGMENT="1">
   <MATNR>FG-1</MATNR><MEINS>KG</MEINS><MTART>FERT</MTART>
   <E1MAKTM SEGMENT="1"><SPRAS>D</SPRAS><MAKTX>Schaum</MAKTX></E1MAKTM>
   <E1MAKTM SEGMENT="1"><SPRAS>E</SPRAS><MAKTX>Foam</MAKTX></E1MAKTM>
   <E1MARCM SEGMENT="1"><WERKS>1010</WERKS></E1MARCM>
   <E1MARCM SEGMENT="1"><WERKS>1020</WERKS></E1MARCM>
  </E1MARAM>
 </IDOC>
</MATMAS05>"""

BATMAS = b"""<BATMAS03>
 <IDOC BEGIN="1">
  <EDI_DC40 SEGMENT="1"><DOCNUM>42</DOCNUM><MESTYP>BATMAS</MESTYP><SNDPRN>S4H</SNDPRN></EDI_DC40>
  <E1BATMAS SEGMENT="1"><MATERIAL>FG-1</MATERIAL><PLANT>%s</PLANT><BATCH>B001</BATCH></E1BATMAS>
 </IDOC>
</BATMAS03>"""


class TestParse(unittest.TestCase):
	def test_str_input(self):
		[parsed] = idoc.parse(LOIPRO.decode())
		self.assertEqual(parsed.message_type, "LOIPRO")

	def test_control_record_is_filtered_and_stripped(self):
		[parsed] = idoc.parse(MATMAS)
		self.assertEqual(parsed.control["DOCNUM"], "0000000000000777")
		self.assertEqual(parsed.control["CREDAT"], "20261030")
		self.assertNotIn("ZZCUSTOM", parsed.control)
		self.assertNotIn("CIMTYP", parsed.control)  # absent fields are not invented
		self.assertEqual(parsed.number, "777")
		self.assertEqual(parsed.sender, "S4HCLNT100")

	def test_zero_document_number(self):
		xml = BATMAS.replace(b"<DOCNUM>42</DOCNUM>", b"<DOCNUM>0000</DOCNUM>") % b""
		self.assertEqual(idoc.parse(xml)[0].number, "0")

	def test_segments_nest_and_repeat(self):
		[parsed] = idoc.parse(MATMAS)
		material = parsed.segments["E1MARAM"][0]
		self.assertEqual(material["MATNR"], "FG-1")
		self.assertEqual([t["MAKTX"] for t in material["E1MAKTM"]], ["Schaum", "Foam"])
		self.assertEqual([p["WERKS"] for p in material["E1MARCM"]], ["1010", "1020"])

	def test_several_idocs_in_one_post(self):
		xml = b"<LOIPRO01>" + LOIPRO.split(b"<LOIPRO01>")[1].replace(b"</LOIPRO01>", b"") * 2 + b"</LOIPRO01>"
		self.assertEqual(len(idoc.parse(xml)), 2)

	def test_idoc_as_root_element(self):
		inner = LOIPRO.split(b"\n", 1)[1]  # drop the XML declaration
		inner = inner.replace(b"<LOIPRO01>", b"").replace(b"</LOIPRO01>", b"")
		[parsed] = idoc.parse(inner)
		self.assertEqual(parsed.message_type, "LOIPRO")

	def test_namespaced_tags(self):
		xml = b"""<ns:LOIPRO01 xmlns:ns="urn:sap"><ns:IDOC><ns:EDI_DC40><ns:DOCNUM>1</ns:DOCNUM><ns:MESTYP>LOIPRO</ns:MESTYP></ns:EDI_DC40>
		<ns:E1AFKOL><ns:AUFNR>000001</ns:AUFNR></ns:E1AFKOL></ns:IDOC></ns:LOIPRO01>"""
		[parsed] = idoc.parse(xml)
		self.assertEqual(parsed.message_type, "LOIPRO")
		self.assertEqual(idoc.summarize(parsed)["external_id"], "1")

	def test_empty_elements_and_whitespace(self):
		xml = b"<X><IDOC><EDI_DC40><DOCNUM> 5 </DOCNUM><MESTYP>ZZ</MESTYP><SNDPRN/></EDI_DC40><E1X><F></F></E1X></IDOC></X>"
		[parsed] = idoc.parse(xml)
		self.assertEqual((parsed.number, parsed.sender), ("5", ""))
		self.assertEqual(parsed.segments, {"E1X": [{"F": ""}]})

	def test_malformed_inputs(self):
		for xml in (
			b"<X><IDOC><EDI_DC40><DOCNUM>1</DOCNUM></EDI_DC40></IDOC></X>",  # no MESTYP
			b"<X><IDOC><EDI_DC40><MESTYP>LOIPRO</MESTYP></EDI_DC40></IDOC></X>",  # no DOCNUM
			b"<X><Y/></X>",  # no IDOC anywhere
			b"<X><IDOC>",  # not well-formed
			b"",
			b'<?xml version="1.0"?><!DOCTYPE x SYSTEM "x.dtd"><X/>',
			b"<X>&ent;</X>",
		):
			with self.assertRaises(idoc.IDocError, msg=xml):
				idoc.parse(xml)

	def test_entity_declaration_deep_in_the_document_is_refused(self):
		xml = b"<X>" + b" " * 5000 + b"<!ENTITY a 'b'></X>"
		with self.assertRaises(idoc.IDocError):
			idoc.parse(xml)

	def test_local_and_first_helpers(self):
		self.assertEqual(idoc.local("{urn:sap}IDOC"), "IDOC")
		self.assertEqual(idoc.local("IDOC"), "IDOC")
		self.assertEqual(idoc.first({"A": [{"x": 1}]}, "A"), {"x": 1})
		self.assertEqual(idoc.first({"A": []}, "A"), {})
		self.assertEqual(idoc.first({}, "A"), {})

	def test_idoc_dataclass_defaults(self):
		doc = idoc.IDoc(control={})
		self.assertEqual((doc.number, doc.message_type, doc.sender, doc.segments), ("0", "", "", {}))


class TestSummaries(unittest.TestCase):
	def test_order_download(self):
		summary = idoc.summarize(idoc.parse(LOIPRO)[0])
		self.assertEqual(summary["material"], "FG-1")
		self.assertEqual(
			(summary["quantity"], summary["unit"], summary["order_type"]), ("100.000", "KG", "PP01")
		)
		self.assertEqual(
			summary["operations"][1], {"operation": "0020", "work_center": "CURE01", "description": "Cure"}
		)

	def test_order_without_operations_or_header(self):
		xml = b"<X><IDOC><EDI_DC40><DOCNUM>1</DOCNUM><MESTYP>LOIPRO</MESTYP></EDI_DC40><E1AFKOL><AUFNR>007</AUFNR></E1AFKOL></IDOC></X>"
		summary = idoc.summarize(idoc.parse(xml)[0])
		self.assertEqual((summary["external_id"], summary["operations"], summary["plant"]), ("7", [], ""))
		xml = b"<X><IDOC><EDI_DC40><DOCNUM>1</DOCNUM><MESTYP>LOIPRO</MESTYP></EDI_DC40></IDOC></X>"
		summary = idoc.summarize(idoc.parse(xml)[0])
		self.assertEqual((summary["reference_type"], summary["external_id"]), ("Work Order", ""))

	def test_material_master(self):
		summary = idoc.summarize(idoc.parse(MATMAS)[0])
		self.assertEqual(
			summary,
			{"reference_type": "Item", "external_id": "FG-1", "base_unit": "KG", "description": "Schaum"},
		)

	def test_material_without_description(self):
		xml = b"<X><IDOC><EDI_DC40><DOCNUM>1</DOCNUM><MESTYP>MATMAS</MESTYP></EDI_DC40><E1MARAM><MATNR>M</MATNR></E1MARAM></IDOC></X>"
		summary = idoc.summarize(idoc.parse(xml)[0])
		self.assertEqual(
			(summary["external_id"], summary["description"], summary["base_unit"]), ("M", "", "")
		)

	def test_batch_with_and_without_plant(self):
		summary = idoc.summarize(idoc.parse(BATMAS % b"1010")[0])
		self.assertEqual(
			summary, {"reference_type": "Batch", "external_id": "FG-1|1010|B001", "plant": "1010"}
		)
		summary = idoc.summarize(idoc.parse(BATMAS % b"")[0])
		self.assertEqual(summary["external_id"], "FG-1|B001")
		self.assertEqual(summary["plant"], "")

	def test_batch_external_id_matches_the_entity_key(self):
		from foames.foames_adapters.s4hana.entities import DEFAULT_ENTITIES

		spec = DEFAULT_ENTITIES["Batch"]
		for plant in (b"1010", b""):
			external_id = idoc.summarize(idoc.parse(BATMAS % plant)[0])["external_id"]
			keys = spec.keys_for(external_id)
			self.assertEqual(
				(keys["Material"], keys["Batch"], keys["BatchIdentifyingPlant"]),
				("FG-1", "B001", plant.decode()),
			)

	def test_unknown_and_empty_message_types(self):
		self.assertEqual(idoc.summarize(idoc.IDoc(control={"MESTYP": "ZFOO"})), {})
		self.assertEqual(idoc.summarize(idoc.IDoc(control={})), {})


if __name__ == "__main__":
	unittest.main()
