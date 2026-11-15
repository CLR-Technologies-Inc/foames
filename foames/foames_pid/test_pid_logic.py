# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Frappe-free P&ID core: ISA-5.1 tags, DEXPI import, SVG, links, register, overlay.

Runs with plain unittest. The fixtures under test_data/ are small P&IDs written for these tests
in the DEXPI 1.3 and 2.0 forms.
"""

import os
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from foames.foames_pid import dexpi, isa51, linking, overlay, register, svg

HERE = os.path.dirname(__file__)


def fixture(name: str) -> bytes:
	with open(os.path.join(HERE, "test_data", name), "rb") as handle:
		return handle.read()


class TestISA51(unittest.TestCase):
	def test_common_tags(self):
		cases = {
			"FIC-101": ("Flow indicate control", "F-101", ["I", "C"]),
			"PDT-2003A": ("Differential pressure transmit", "P-2003", ["T"]),
			"10-LSHH-305": ("Level switch high high", "10-L-305", ["S"]),
			"PSV-12": ("Pressure safety valve", "P-12", ["V"]),
			"FQI 7": ("Flow integrate indicate", "F-7", ["I"]),
			"HS-1": ("Hand switch", "H-1", ["S"]),
			"LAL-4": ("Level alarm low", "L-4", ["A"]),
			"FFIC-9": ("Flow ratio indicate control", "F-9", ["I", "C"]),
			"PI4712.01": ("Pressure indicate", "P-4712.01", ["I"]),
			"TT_101": ("Temperature transmit", "T-101", ["T"]),
		}
		for tag, (meaning, loop, functions) in cases.items():
			with self.subTest(tag=tag):
				parsed = isa51.parse_tag(tag)
				self.assertEqual(parsed.meaning, meaning)
				self.assertEqual(parsed.loop, loop)
				self.assertEqual(parsed.functions, functions)
				self.assertEqual(parsed.warnings, [])

	def test_flags(self):
		self.assertTrue(isa51.parse_tag("FIC-101").reads_value)
		self.assertTrue(isa51.parse_tag("LSHH-1").is_switch)
		self.assertFalse(isa51.parse_tag("LSHH-1").reads_value)
		self.assertTrue(isa51.parse_tag("LAL-1").is_alarm)
		self.assertTrue(isa51.parse_tag("FV-101").is_final_element)

	def test_suffix_and_area(self):
		parsed = isa51.parse_tag("TT 101 A")
		self.assertEqual((parsed.tag, parsed.suffix, parsed.loop_number), ("TT-101-A", "A", "101"))
		parsed = isa51.parse_tag("2-PT-55B")
		self.assertEqual((parsed.area, parsed.suffix, parsed.loop), ("2", "B", "2-P-55"))

	def test_user_legend(self):
		parsed = isa51.parse_tag("MI-3", legend={"first": {"M": "Moisture"}})
		self.assertEqual(parsed.meaning, "Moisture indicate")

	def test_not_a_tag(self):
		for text in ("", "pump", "101", "FIC-"):
			with self.subTest(text=text):
				self.assertIsNone(isa51.try_parse_tag(text))
		with self.assertRaises(isa51.TagError):
			isa51.parse_tag("not a tag")

	def test_unknown_letters_are_warned(self):
		self.assertIn("F is not a succeeding letter", isa51.parse_tag("PF-1").warnings)

	def test_keys_and_compose(self):
		self.assertEqual(isa51.tag_key("fic_101"), "FIC101")
		self.assertEqual(isa51.normalise(" fic  _101 "), "FIC-101")
		self.assertEqual(isa51.compose_tag("P", "ICSA", "4712.02"), "PICSA4712.02")
		self.assertEqual(isa51.compose_tag("F", "IC", "101", separator="-"), "FIC-101")


class TestDexpi13(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.diagram = dexpi.parse(fixture("feed_system_dexpi13.xml"))
		cls.by_tag = {c.tag: c for c in cls.diagram.components}

	def test_header(self):
		d = self.diagram
		self.assertEqual((d.drawing_number, d.revision, d.title), ("PID-100-001", "B", "Feed system"))
		self.assertEqual(d.dexpi_version, "1.3")
		self.assertEqual(d.extent, (0.0, 0.0, 420.0, 297.0))
		self.assertEqual(d.warnings, [])

	def test_register(self):
		types = {tag: c.component_type for tag, c in self.by_tag.items()}
		self.assertEqual(
			types,
			{
				"TK-101": "Equipment",
				"P-101": "Equipment",
				"E-101": "Equipment",
				"1001": "Line",
				"1002": "Line",
				"PSV-103": "Valve",
				"FIC-101": "Instrument",
				"FT-101": "Instrument",
				"TI-102": "Instrument",
				"FV-101": "Valve",
			},
		)
		self.assertNotIn("NOT-A-TAG", self.by_tag)  # the shape catalogue is not the plant
		self.assertEqual(self.by_tag["TK-101"].description, "Feed tank")
		self.assertEqual(
			self.by_tag["TK-101"].attributes["NominalCapacityVolume"], {"value": "12", "units": "MetreCubed"}
		)
		self.assertEqual(self.by_tag["1002"].description, "DN 50 PW")
		self.assertEqual(self.by_tag["FIC-101"].description, "")  # the ISA meaning is not file data
		self.assertEqual(self.by_tag["FIC-101"].component_class, "CentralLocation")
		self.assertEqual(self.by_tag["FIC-101"].loop_number, "101")

	def test_where_things_are(self):
		self.assertEqual(self.by_tag["FIC-101"].parent_tag, "1002")  # FT-101 sits in the orifice on 1002
		self.assertEqual(self.by_tag["FT-101"].parent_tag, "FIC-101")
		self.assertEqual(self.by_tag["TI-102"].parent_tag, "TK-101")  # through the tank's nozzle
		self.assertEqual(self.by_tag["FV-101"].parent_tag, "1002")  # the valve the actuating system operates
		self.assertEqual(self.by_tag["PSV-103"].parent_tag, "1002")

	def test_connections_follow_the_piping(self):
		process = {(c.from_tag, c.to_tag, c.via) for c in self.diagram.connections if c.kind == "Process"}
		self.assertEqual(process, {("TK-101", "P-101", "1001"), ("P-101", "E-101", "1002")})
		signal = {(c.from_tag, c.to_tag) for c in self.diagram.connections if c.kind == "Signal"}
		self.assertIn(("TK-101", "TI-102"), signal)
		self.assertIn(("FIC-101", "FT-101"), signal)

	def test_view(self):
		view = self.diagram.view()
		tagged = {i["tag"] for i in view["items"] if i["tag"]}
		self.assertTrue({"TK-101", "P-101", "E-101", "FIC-101", "TI-102", "FV-101", "PSV-103"} <= tagged)
		kinds = {line["kind"] for line in view["lines"]}
		self.assertEqual(kinds, {"Process", "Measuring", "Signal"})
		self.assertTrue(all(len(line["points"]) >= 2 for line in view["lines"]))


class TestDexpi20(unittest.TestCase):
	def test_same_plant_from_the_model_form(self):
		diagram = dexpi.parse(fixture("feed_system_dexpi20.xml"))
		self.assertEqual(
			(diagram.drawing_number, diagram.revision, diagram.dexpi_version), ("PID-100-002", "A", "2.0.0")
		)
		by_tag = {c.tag: c for c in diagram.components}
		self.assertEqual(set(by_tag), {"TK-101", "P-101", "1001", "TI-102"})
		self.assertEqual(
			by_tag["TK-101"].attributes["NominalCapacityVolume"], {"value": "12.0", "units": "MetreCubed"}
		)
		self.assertEqual(by_tag["TI-102"].parent_tag, "TK-101")
		self.assertEqual(by_tag["TI-102"].component_class, "Field")
		process = [(c.from_tag, c.to_tag, c.via) for c in diagram.connections if c.kind == "Process"]
		self.assertEqual(process, [("TK-101", "P-101", "1001")])
		view = diagram.view()
		positions = {i["tag"]: (i["x"], i["y"]) for i in view["items"] if i["tag"]}
		self.assertEqual(positions["TK-101"], (60.0, 150.0))
		self.assertEqual(view["lines"][0]["points"], [[70.0, 120.0], [100.0, 120.0]])


class TestDexpiRefusals(unittest.TestCase):
	def test_entities_are_refused(self):
		payload = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><PlantModel>&a;</PlantModel>'
		with self.assertRaisesRegex(dexpi.DexpiError, "DOCTYPE"):
			dexpi.parse(payload)

	def test_not_xml_or_not_dexpi(self):
		with self.assertRaisesRegex(dexpi.DexpiError, "not XML"):
			dexpi.parse(b"Tag,Type\nFIC-101,Instrument\n")
		with self.assertRaisesRegex(dexpi.DexpiError, "well-formed"):
			dexpi.parse(b"<PlantModel><Equipment></PlantModel>")
		with self.assertRaisesRegex(dexpi.DexpiError, "PlantModel"):
			dexpi.parse(b"<svg/>")

	def test_process_model_is_not_a_pid(self):
		payload = b'<Model><Object type="Process/ProcessModel"/></Model>'
		with self.assertRaisesRegex(dexpi.DexpiError, "process model"):
			dexpi.parse(payload)

	def test_duplicate_tags_are_warned(self):
		payload = b"""<PlantModel>
			<Equipment ID="A" ComponentClass="Tank"><GenericAttributes><GenericAttribute Name="TagNameAssignmentClass" Value="T-1"/></GenericAttributes></Equipment>
			<Equipment ID="B" ComponentClass="Tank"><GenericAttributes><GenericAttribute Name="TagNameAssignmentClass" Value="T-1"/></GenericAttributes></Equipment>
		</PlantModel>"""
		diagram = dexpi.parse(payload)
		self.assertEqual(len(diagram.components), 1)
		self.assertIn("appears more than once", diagram.warnings[0])


class TestSvg(unittest.TestCase):
	def test_render_marks_tags_and_overlays_values(self):
		view = dexpi.parse(fixture("feed_system_dexpi13.xml")).view()
		out = svg.render_svg(
			view,
			{"P-101": {"state": "Down"}, "FIC-101": {"value": 12.345, "unit": "m3/h", "flag": "high"}},
			{"P-101": "Feed pump <A&B>"},
		)
		root = ET.fromstring(out)  # well-formed
		ns = "{http://www.w3.org/2000/svg}"
		groups = {g.get("data-tag"): g for g in root.iter(f"{ns}g") if g.get("data-tag")}
		self.assertIn("Down", groups["P-101"].get("class"))
		self.assertIn("flag-high", groups["FIC-101"].get("class"))
		texts = [t.text for t in groups["FIC-101"].iter(f"{ns}text")]
		self.assertIn("12.3 m3/h", texts)  # three significant figures
		self.assertEqual(groups["P-101"].find(f"{ns}title").text, "P-101 - Feed pump <A&B>")
		self.assertNotIn("NOT-A-TAG", out)

	def test_escapes_hostile_tags(self):
		view = {
			"extent": [0, 0, 100, 100],
			"items": [{"kind": "Equipment", "tag": '"><script>x</script>', "x": 1, "y": 1}],
			"lines": [],
		}
		out = svg.render_svg(view)
		self.assertNotIn("<script>", out)
		ET.fromstring(out)

	def test_auto_layout_orders_equipment_by_flow(self):
		components = [
			{"tag": "E-101", "component_type": "Equipment"},
			{"tag": "P-101", "component_type": "Equipment", "component_class": "CentrifugalPump"},
			{"tag": "TK-101", "component_type": "Equipment"},
			{"tag": "1002", "component_type": "Line"},
			{"tag": "FIC-101", "component_type": "Instrument", "parent_tag": "1002"},
			{"tag": "TI-102", "component_type": "Instrument", "parent_tag": "TK-101"},
			{"tag": "XA-9", "component_type": "Instrument"},
		]
		connections = [
			{"kind": "Process", "from_tag": "TK-101", "to_tag": "P-101", "via": "1001"},
			{"kind": "Process", "from_tag": "P-101", "to_tag": "E-101", "via": "1002"},
		]
		view = svg.auto_layout(components, connections)
		x = {i["tag"]: i["x"] for i in view["items"]}
		self.assertLess(x["TK-101"], x["P-101"])
		self.assertLess(x["P-101"], x["E-101"])
		self.assertAlmostEqual(x["FIC-101"], x["P-101"], delta=10)  # on 1002, which leaves P-101
		self.assertAlmostEqual(x["TI-102"], x["TK-101"], delta=10)
		self.assertNotIn("1002", x)  # a line is not a symbol
		self.assertEqual(len(view["lines"]), 2)
		ET.fromstring(svg.render_svg(view))


class TestLinking(unittest.TestCase):
	def test_matches(self):
		self.assertEqual(linking.matches("FIC-101", "FIC_101"), "exact")
		self.assertEqual(linking.matches("FIC-101", "ns=2;s=[default]Area1/FIC_101/PV"), "segment")
		self.assertEqual(linking.matches("FIC-101", "Line1/FIC101PV"), "prefix")
		self.assertEqual(linking.matches("PT4712.01", "Plant/PT4712.01/PV"), "segment")
		self.assertEqual(linking.matches("FIC-101", "FIC-1010"), "")
		self.assertEqual(linking.matches("FIC-101", "Area1/FIC-1010/PV"), "")

	def test_suggest(self):
		components = [
			{"tag": "FIC-101", "component_type": "Instrument"},
			{"tag": "P-101", "component_type": "Equipment"},
			{"tag": "TT-7", "component_type": "Instrument"},
			{"tag": "LSH-3", "component_type": "Instrument"},
			{"tag": "PT-9", "component_type": "Instrument", "machine": "M1", "signal_name": "pt9"},
		]
		machines = [{"name": "P-101", "title": "Feed pump", "source_id": "pump1"}]
		node_maps = [
			{
				"machine": "P-101",
				"source": "OPC UA",
				"node_id": "ns=2;s=[default]A1/FIC_101/PV",
				"event_type": "Measurement",
				"name_or_counter": "feed_flow",
			},
			{
				"machine": "P-101",
				"source": "OPC UA",
				"node_id": "ns=2;s=[default]A1/PT_9/PV",
				"event_type": "Measurement",
				"name_or_counter": "pt9",
			},
		]
		measurements = [
			{"machine": "M2", "measurement_name": "TT7.PV"},
			{"machine": "M2", "measurement_name": "LSH3"},
		]
		found = {s["tag"]: s for s in linking.suggest_links(components, machines, node_maps, measurements)}
		self.assertEqual(found["FIC-101"]["signal_name"], "feed_flow")
		self.assertEqual(found["FIC-101"]["signal_source"], "OPC UA")
		self.assertEqual((found["P-101"]["machine"], found["P-101"]["event_type"]), ("P-101", "State"))
		self.assertEqual((found["TT-7"]["machine"], found["TT-7"]["signal_name"]), ("M2", "TT7.PV"))
		self.assertNotIn("PT-9", found)  # already linked
		self.assertTrue(all(s["reason"] for s in found.values()))


class TestRegister(unittest.TestCase):
	def test_read_loose_headers(self):
		text = (
			"Tag No.,Service,P&ID,URV,LRV,UoM,PI Tag,Vendor\n"
			'FIC 101,Feed flow,D-100,"1,250.5",0,m3/h,U1.FIC101.PV,ACME\n'
			"P-101,Feed pump,D-100,,,,,\n"
			"FIC-101,again,,,,,,\n"
			",no tag,,,,,,\n"
		)
		rows, warnings = register.read_register(text)
		self.assertEqual([r["tag"] for r in rows], ["FIC-101", "P-101"])
		first = rows[0]
		self.assertEqual(first["component_type"], "Instrument")
		self.assertEqual((first["range_low"], first["range_high"]), (0.0, 1250.5))
		self.assertEqual(first["historian_tag"], "U1.FIC101.PV")
		self.assertEqual(first["attributes"], {"Vendor": "ACME"})
		self.assertEqual(rows[1]["component_type"], "Equipment")
		self.assertEqual(len(warnings), 2)

	def test_semicolons_and_decimal_commas(self):
		rows, _ = register.read_register("Tag;Type;LRV;URV\nPT-1;;0;12,5\n")
		self.assertEqual(rows[0]["range_high"], 12.5)

	def test_errors(self):
		with self.assertRaises(register.RegisterError):
			register.read_register("")
		with self.assertRaises(register.RegisterError):
			register.read_register("Name,Value\nx,1\n")
		with self.assertRaisesRegex(register.RegisterError, "not a number"):
			register.read_register("Tag,URV\nPT-1,lots\n")

	def test_round_trip(self):
		rows, _ = register.read_register("Tag,Type,Machine,Signal\nFT-1,Instrument,M1,flow\n")
		again, _ = register.read_register(register.write_register(rows))
		self.assertEqual(
			(again[0]["tag"], again[0]["machine"], again[0]["signal_name"]), ("FT-1", "M1", "flow")
		)

	def test_guess_type(self):
		self.assertEqual(register.guess_type("FIC-101"), "Instrument")
		self.assertEqual(register.guess_type("FV-101"), "Valve")
		self.assertEqual(register.guess_type("P-101"), "Equipment")


INSTRUMENT = {
	"tag": "FT-1",
	"component_type": "Instrument",
	"machine": "M1",
	"event_type": "Measurement",
	"signal_name": "flow",
	"engineering_unit": "m3/h",
	"range_low": 0.0,
	"range_high": 100.0,
}


class TestOverlay(unittest.TestCase):
	now = datetime(2026, 11, 14, 12, 0)
	instrument = INSTRUMENT

	def entry(self, value, minutes_ago=1, component=None):
		last = (
			{"value": value, "timestamp": self.now - timedelta(minutes=minutes_ago)}
			if value is not None
			else None
		)
		return overlay.overlay_entry(component or self.instrument, "Running", last, self.now)

	def test_flags(self):
		self.assertIsNone(self.entry(50)["flag"])
		self.assertEqual(self.entry(100)["flag"], "high")
		self.assertEqual(self.entry(-1)["flag"], "low")
		self.assertEqual(self.entry(50, minutes_ago=90)["flag"], "stale")
		self.assertEqual(self.entry(None)["flag"], "none")
		no_range = {**self.instrument, "range_low": None, "range_high": None}
		self.assertIsNone(self.entry(1e9, component=no_range)["flag"])
		self.assertEqual(self.entry(50)["unit"], "m3/h")
		self.assertIsNone(self.entry(50)["state"])  # an instrument shows its value, not the machine

	def test_equipment_shows_machine_state(self):
		pump = {"tag": "P-1", "component_type": "Equipment", "machine": "M1"}
		self.assertEqual(overlay.overlay_entry(pump, "Down", None, self.now)["state"], "Down")
		self.assertEqual(overlay.overlay_entry(pump, None, None, self.now)["state"], "Unknown")

	def test_findings(self):
		components = [
			{**self.instrument, "tag": "FT-1"},
			{**self.instrument, "tag": "FT-2"},
			{**self.instrument, "tag": "FT-3"},
		]
		entries = {
			"FT-1": self.entry(50),
			"FT-2": self.entry(100),
			"FT-3": self.entry(None),
		}
		findings = {f["reference_name"]: f for f in overlay.signal_findings(components, entries)}
		self.assertEqual(set(findings), {"FT-2", "FT-3"})
		self.assertEqual(findings["FT-2"]["rule_key"], "pid-range-high:FT-2")
		self.assertEqual(findings["FT-3"]["rule_key"], "pid-signal-silent:FT-3")
		for finding in findings.values():
			for key in ("rule_key", "title", "category", "suggestion", "severity", "evidence"):
				self.assertTrue(finding[key])


if __name__ == "__main__":
	unittest.main()
