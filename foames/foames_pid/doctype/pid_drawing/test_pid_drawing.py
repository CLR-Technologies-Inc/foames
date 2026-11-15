# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import os
import xml.etree.ElementTree as ET

import frappe
from frappe.utils import add_to_date, now_datetime

from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
from foames.foames_pid import api, dexpi
from foames.foames_pid.rules import instrument_signals
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "test_data")


def fixture(name):
	with open(os.path.join(FIXTURES, name), "rb") as handle:
		return handle.read()


def make_drawing(number="PID-100-001", **values):
	if frappe.db.exists("PID Drawing", number):
		return frappe.get_doc("PID Drawing", number)
	return frappe.get_doc({"doctype": "PID Drawing", "drawing_number": number, **values}).insert()


def measure(machine, name, value, minutes_ago=5):
	return frappe.get_doc(
		{
			"doctype": "Machine Event",
			"machine": machine,
			"event_type": "Measurement",
			"source": "Manual",
			"measurement_name": name,
			"value": value,
			"timestamp": add_to_date(now_datetime(), minutes=-minutes_ago),
		}
	).insert(ignore_permissions=True)


class TestDexpiImport(IntegrationTestCase):
	def import_fixture(self, number="PID-100-001", name="feed_system_dexpi13.xml"):
		drawing = make_drawing(number, source_format="DEXPI")
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{number}.xml",
				"content": fixture(name),
				"is_private": 1,
				"attached_to_doctype": "PID Drawing",
				"attached_to_name": drawing.name,
			}
		).insert(ignore_permissions=True)
		drawing.source_file = file.file_url
		drawing.save()
		result = drawing.import_dexpi()
		return frappe.get_doc("PID Drawing", drawing.name), result

	def test_import_fills_the_register_and_the_drawing(self):
		drawing, result = self.import_fixture()
		self.assertEqual(len(result["created"]), 10)
		self.assertEqual(
			(drawing.title, drawing.revision, drawing.dexpi_version), ("Feed system", "B", "1.3")
		)
		self.assertEqual(drawing.component_count, 10)
		fic = frappe.get_doc("PID Component", "FIC-101")
		self.assertEqual(
			(fic.component_type, fic.parent_component, fic.drawing), ("Instrument", "1002", drawing.name)
		)
		self.assertEqual(fic.isa_meaning, "Flow indicate control")
		self.assertEqual(fic.functions, "I, C")
		tank = frappe.get_doc("PID Component", "TK-101")
		self.assertEqual(tank.description, "Feed tank")
		self.assertIn("NominalCapacityVolume", {a.attribute for a in tank.attributes})
		process = {
			(r.from_component, r.to_component, r.via) for r in drawing.connections if r.kind == "Process"
		}
		self.assertEqual(process, {("TK-101", "P-101", "1001"), ("P-101", "E-101", "1002")})
		view = api.get_drawing_view(drawing.name)
		ET.fromstring(view["svg"])
		self.assertIn("FIC-101", view["tags"])

	def test_reimport_keeps_what_people_set(self):
		make_machine("T-PID-PUMP")
		drawing, _ = self.import_fixture()
		fic = frappe.get_doc("PID Component", "FIC-101")
		fic.update(
			{
				"machine": "T-PID-PUMP",
				"signal_name": "feed_flow",
				"description": "Feed flow to E-101",
				"range_low": 0,
				"range_high": 40,
			}
		)
		fic.save()
		frappe.db.set_value("PID Component", "FT-101", "drawing", None)  # as if typed in by hand
		_, result = self.import_fixture()
		self.assertIn("FIC-101", result["updated"])
		fic.reload()
		self.assertEqual((fic.machine, fic.signal_name, fic.range_high), ("T-PID-PUMP", "feed_flow", 40))
		self.assertEqual(fic.description, "Feed flow to E-101")  # the file has no description for it
		self.assertEqual(frappe.db.get_value("PID Component", "FT-101", "drawing"), drawing.name)

	def test_a_tag_owned_by_another_drawing_is_left_alone(self):
		other = make_drawing("PID-100-099")
		frappe.get_doc(
			{
				"doctype": "PID Component",
				"tag": "1002",
				"component_type": "Line",
				"drawing": other.name,
				"description": "Owned",
			}
		).insert()
		drawing, result = self.import_fixture()
		self.assertIn("1002", result["elsewhere"])
		self.assertEqual(frappe.db.get_value("PID Component", "1002", "description"), "Owned")
		self.assertIn("another drawing", drawing.import_summary)

	def test_dexpi_2_imports_the_same_way(self):
		drawing, result = self.import_fixture("PID-100-002", "feed_system_dexpi20.xml")
		self.assertEqual(set(result["created"]), {"TK-101", "P-101", "1001", "TI-102"})
		self.assertEqual(frappe.db.get_value("PID Component", "TI-102", "parent_component"), "TK-101")
		self.assertEqual(drawing.dexpi_version, "2.0.0")

	def test_a_bad_file_is_refused_with_a_reason(self):
		drawing = make_drawing("PID-BAD", source_format="DEXPI")
		file = frappe.get_doc(
			{"doctype": "File", "file_name": "bad.xml", "content": b"<svg/>", "is_private": 1}
		).insert(ignore_permissions=True)
		drawing.source_file = file.file_url
		drawing.save()
		with self.assertRaisesRegex(frappe.ValidationError, "could not be read"):
			drawing.import_dexpi()


class TestLiveSignals(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.machine = make_machine("T-PID-M1").name
		drawing = make_drawing("PID-T-LIVE")
		drawing.apply_diagram(dexpi.parse(fixture("feed_system_dexpi13.xml")))
		self.drawing = drawing.name

	def link(self, tag, **values):
		doc = frappe.get_doc("PID Component", tag)
		doc.update({"machine": self.machine, **values})
		doc.save()
		return doc

	def test_viewer_overlays_state_and_values(self):
		frappe.db.set_value("Machine", self.machine, "status", "Down")
		self.link("P-101")
		self.link("FIC-101", signal_name="flow", range_low=0, range_high=40, engineering_unit="m3/h")
		measure(self.machine, "flow", 12.5, minutes_ago=30)
		measure(self.machine, "flow", 41.0, minutes_ago=2)
		view = api.get_drawing_view(self.drawing)
		self.assertEqual(view["overlay"]["P-101"]["state"], "Down")
		self.assertEqual(view["overlay"]["FIC-101"]["value"], 41.0)
		self.assertEqual(view["overlay"]["FIC-101"]["flag"], "high")
		root = ET.fromstring(view["svg"])
		classes = {g.get("data-tag"): g.get("class") for g in root.iter("{http://www.w3.org/2000/svg}g")}
		self.assertIn("Down", classes["P-101"])
		self.assertIn("flag-high", classes["FIC-101"])
		component = api.get_component("fic-101")
		self.assertEqual(component["isa"]["meaning"], "Flow indicate control")
		self.assertEqual(component["live"]["value"], 41.0)
		self.assertIn("FT-101", component["children"])

	def test_rule_raises_silent_and_pinned_signals(self):
		self.link("FIC-101", signal_name="flow", range_low=0, range_high=40)
		self.link("TI-102", signal_name="tank_temp")  # never reports
		measure(self.machine, "flow", 40.0)
		findings = {f["reference_name"]: f for f in instrument_signals({})}
		self.assertEqual(findings["FIC-101"]["rule_key"], "pid-range-high:FIC-101")
		self.assertEqual(findings["TI-102"]["rule_key"], "pid-signal-silent:TI-102")
		names = raise_suggestions(list(findings.values()), agent="foames-pid-test")
		self.assertEqual(len(names), 2)
		self.assertEqual(
			raise_suggestions(list(findings.values()), agent="foames-pid-test"), []
		)  # no repeats

	def test_signal_needs_a_machine(self):
		doc = frappe.get_doc("PID Component", "TI-102")
		doc.signal_name = "tank_temp"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_suggest_and_apply_links(self):
		measure(self.machine, "Area1/FIC_101/PV", 3.0)
		suggestions = {s["tag"]: s for s in api.suggest_links(self.drawing)}
		self.assertEqual(suggestions["FIC-101"]["machine"], self.machine)
		self.assertEqual(suggestions["FIC-101"]["signal_name"], "Area1/FIC_101/PV")
		self.assertEqual(api.apply_links([suggestions["FIC-101"]]), ["FIC-101"])
		self.assertEqual(frappe.db.get_value("PID Component", "FIC-101", "signal_name"), "Area1/FIC_101/PV")

	def test_operator_reads_but_cannot_link(self):
		make_user("pid-operator@example.com", "FoaMES Operator")
		with as_user("pid-operator@example.com"):
			self.assertTrue(api.list_components(drawing=self.drawing))
			with self.assertRaises(frappe.PermissionError):
				api.apply_links([{"tag": "FIC-101", "machine": self.machine, "signal_name": "x"}])
			with self.assertRaises(frappe.PermissionError):
				api.import_tag_register("Tag\nXT-1\n")


class TestTagRegister(IntegrationTestCase):
	def test_import_and_export(self):
		make_machine("T-PID-REG")
		drawing = make_drawing("PID-T-REG")
		text = (
			"Tag No.,Type,Service,P&ID,Machine,Measurement,URV,LRV,UoM,Located On,Vendor\n"
			"P-201,Equipment,Transfer pump,PID-T-REG,T-PID-REG,,,,,,\n"
			"PT-201,,Discharge pressure,PID-T-REG,T-PID-REG,discharge_pressure,16,0,bar,P-201,ACME\n"
			"TT-202,,Missing machine,PID-T-REG,NO-SUCH-MACHINE,t,,,,,\n"
		)
		result = api.import_tag_register(text)
		self.assertEqual(set(result["created"]), {"P-201", "PT-201", "TT-202"})
		self.assertTrue(any("NO-SUCH-MACHINE" in w for w in result["warnings"]))
		pt = frappe.get_doc("PID Component", "PT-201")
		self.assertEqual(
			(pt.component_type, pt.parent_component, pt.event_type), ("Instrument", "P-201", "Measurement")
		)
		self.assertEqual((pt.range_low, pt.range_high, pt.engineering_unit), (0, 16, "bar"))
		self.assertIsNone(frappe.db.get_value("PID Component", "TT-202", "machine"))
		csv_text = api.export_tag_register(drawing.name)
		self.assertIn("PT-201,Instrument", csv_text)
		# A manual drawing still renders, laid out from the register.
		view = api.get_drawing_view(drawing.name)
		self.assertIn('data-tag="P-201"', view["svg"])
		# Importing again updates, and a blank cell leaves the value as it was.
		result = api.import_tag_register("Tag,Service,URV\nPT-201,Pump discharge pressure,\n")
		self.assertEqual(result["updated"], ["PT-201"])
		pt.reload()
		self.assertEqual((pt.description, pt.range_high), ("Pump discharge pressure", 16))

	def test_parent_loop_is_refused(self):
		frappe.get_doc({"doctype": "PID Component", "tag": "V-301", "component_type": "Equipment"}).insert()
		frappe.get_doc(
			{
				"doctype": "PID Component",
				"tag": "LT-301",
				"component_type": "Instrument",
				"parent_component": "V-301",
			}
		).insert()
		vessel = frappe.get_doc("PID Component", "V-301")
		vessel.parent_component = "LT-301"
		with self.assertRaises(frappe.ValidationError):
			vessel.save()
