# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Commissioning on a site: tests and their steps, the sequence, loop checks, punch items, readiness,
acceptance, handover, the hooks, the daily suggestions and the reports."""

import frappe
from frappe.utils import add_days, getdate, nowdate

from foames.foames_commissioning.doctype.commissioning_package.commissioning_package import (
	check_commissioning,
	get_handover_dossier,
	get_readiness,
)
from foames.foames_commissioning.report.commissioning_status.commissioning_status import (
	execute as commissioning_status,
)
from foames.foames_commissioning.report.punch_list.punch_list import execute as punch_list
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, extra_hooks, make_machine, make_user

OPS = "cm-ops@example.com"
MNT = "cm-maint@example.com"
HANDED_OVER = []


def record_handover(package):
	HANDED_OVER.append(package.name)


def qualification_blocker(package):
	return [{"kind": "Qualification", "reference": None, "message": "IQ protocol is not approved"}]


def make_package(**overrides):
	values = {
		"doctype": "Commissioning Package",
		"title": "Filling line 2",
		"line": "T-CM-LINE",
		"items": [
			{"equipment_tag": "FIL-201", "description": "Rotary filler", "machine": "T-CM-FIL"},
			{"equipment_tag": "CAP-202", "description": "Capper"},
		],
		"require_fat": 1,
		"require_mechanical_completion": 0,
		"require_sat": 0,
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_template(name="T-CM FAT filler", test_type="FAT", **overrides):
	if frappe.db.exists("Commissioning Checklist Template", name):
		return frappe.get_doc("Commissioning Checklist Template", name)
	values = {
		"doctype": "Commissioning Checklist Template",
		"template_name": name,
		"test_type": test_type,
		"items": [
			{
				"section": "Safety",
				"check_text": "Emergency stop stops all drives",
				"kind": "Check",
				"punch_category": "A",
			},
			{
				"section": "Performance",
				"check_text": "Fill weight at nominal speed",
				"kind": "Value",
				"low_limit": "498",
				"high_limit": "502",
				"unit": "g",
			},
		],
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_test(package, test_type="FAT", **overrides):
	values = {"doctype": "Commissioning Test", "package": package, "test_type": test_type}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def pass_test(test, performer="Administrator"):
	for step in test.steps:
		if step.kind == "Value":
			step.measured_value = "500"
		else:
			step.result = "Pass"
	test.performed_by = performer
	test.save()
	return test


def reload(doc):
	return frappe.get_doc(doc.doctype, doc.name)


class TestCommissioning(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-CM-FIL", disabled=1)
		make_user(OPS, "FoaMES Supervisor")
		make_user(MNT, "FoaMES Maintenance")
		HANDED_OVER.clear()

	# Tests and steps

	def test_template_steps_and_value_judgement(self):
		package = make_package()
		test = make_test(package.name, template=make_template().name, equipment_tag="FIL-201")
		self.assertEqual(len(test.steps), 2)
		self.assertEqual(test.machine, "T-CM-FIL")
		self.assertEqual(test.status, "Not Started")
		test.steps[1].measured_value = "500.5"
		test.save()
		self.assertEqual(test.steps[1].result, "Pass")
		self.assertEqual(test.status, "In Progress")
		self.assertIsNotNone(test.started_on)
		test.steps[0].result = "Pass"
		test.save()
		self.assertEqual(test.status, "Awaiting Sign-off")
		test.performed_by = "Administrator"
		test.save()
		self.assertEqual(test.status, "Passed")
		self.assertIsNotNone(test.completed_on)

	def test_failed_step_raises_one_punch_item(self):
		package = make_package()
		test = make_test(package.name, template=make_template().name, equipment_tag="FIL-201")
		test.steps[0].result = "Fail"
		test.steps[0].remarks = "Capper drive keeps running"
		test.save()
		self.assertEqual(test.status, "Failed")
		test = reload(test)
		punch_name = test.steps[0].punch_item
		self.assertTrue(punch_name)
		punch = frappe.get_doc("Punch Item", punch_name)
		self.assertEqual(
			(punch.category, punch.equipment_tag, punch.source_name, punch.source_step),
			("A", "FIL-201", test.name, 1),
		)
		test.save()
		self.assertEqual(frappe.db.count("Punch Item", {"source_name": test.name}), 1)
		self.assertEqual(reload(package).open_punch_a, 1)

	def test_non_numeric_reading_is_refused(self):
		package = make_package()
		test = make_test(package.name, template=make_template().name)
		test.steps[1].measured_value = "about 500"
		with self.assertRaises(frappe.ValidationError):
			test.save()

	def test_witness_is_required_when_the_template_says_so(self):
		package = make_package()
		template = make_template("T-CM witnessed FAT", witness_required=1)
		test = pass_test(make_test(package.name, template=template.name))
		self.assertTrue(test.witness_required)
		self.assertEqual(test.status, "Awaiting Sign-off")
		test.witnessed_by = "Customer QA"
		test.save()
		self.assertEqual(test.status, "Passed")
		self.assertIsNotNone(test.witnessed_on)

	def test_template_must_match_the_test_type(self):
		package = make_package()
		with self.assertRaises(frappe.ValidationError):
			make_test(package.name, test_type="SAT", template=make_template().name)

	def test_equipment_must_be_in_scope(self):
		package = make_package()
		with self.assertRaises(frappe.ValidationError):
			make_test(package.name, equipment_tag="NOT-IN-SCOPE")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Punch Item", "package": package.name, "title": "x", "equipment_tag": "NOPE"}
			).insert()

	def test_duplicate_tags_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_package(items=[{"equipment_tag": "A-1"}, {"equipment_tag": "A-1"}])

	def test_sequence_is_enforced(self):
		package = make_package()
		template = make_template()
		fat = make_test(package.name, template=template.name, equipment_tag="FIL-201")
		sat = make_test(package.name, test_type="SAT", equipment_tag="FIL-201")
		sat.append("steps", {"check_text": "Runs at rate", "kind": "Check", "result": "Pass"})
		with self.assertRaises(frappe.ValidationError):
			sat.save()
		# Another machine's SAT is not held by this machine's FAT.
		other = make_test(package.name, test_type="SAT", equipment_tag="CAP-202")
		other.append("steps", {"check_text": "Runs at rate", "kind": "Check", "result": "Pass"})
		other.save()
		self.assertEqual(other.status, "Awaiting Sign-off")
		pass_test(fat)
		sat = reload(sat)
		sat.append("steps", {"check_text": "Runs at rate", "kind": "Check", "result": "Pass"})
		sat.save()
		self.assertEqual(sat.status, "Awaiting Sign-off")

	def test_sequence_can_be_switched_off(self):
		package = make_package(enforce_sequence=0)
		make_test(package.name, template=make_template().name, equipment_tag="FIL-201")
		sat = make_test(package.name, test_type="SAT", equipment_tag="FIL-201")
		sat.append("steps", {"check_text": "Runs at rate", "kind": "Check", "result": "Pass"})
		sat.save()
		self.assertEqual(sat.status, "Awaiting Sign-off")

	# Loop checks

	def test_analog_loop_check(self):
		package = make_package()
		loop = frappe.get_doc(
			{
				"doctype": "Loop Check",
				"package": package.name,
				"tag": "PT-101",
				"loop_type": "Analog Input",
				"equipment_tag": "FIL-201",
				"range_low": 0,
				"range_high": 10,
				"engineering_unit": "bar",
			}
		).insert()
		self.assertEqual([p.expected_value for p in loop.points], [0, 2.5, 5, 7.5, 10])
		self.assertEqual(loop.status, "Not Started")
		for point, reading in zip(loop.points, ("0.02", "2.5", "5.05", "7.45", "10.0"), strict=True):
			point.as_found = reading
		loop.save()
		self.assertEqual(loop.status, "In Progress")
		loop.checked_by = "Administrator"
		loop.save()
		self.assertEqual(loop.status, "Passed")
		self.assertIsNotNone(loop.checked_on)
		self.assertEqual(reload(package).loop_checks_passed, "1 of 1")

	def test_failed_loop_raises_category_a_punch(self):
		package = make_package()
		loop = frappe.get_doc(
			{"doctype": "Loop Check", "package": package.name, "tag": "XV-110", "loop_type": "Digital Output"}
		).insert()
		self.assertEqual([p.expected_state for p in loop.points], ["On", "Off"])
		loop.points[0].observed_state = "On"
		loop.points[1].observed_state = "On"
		loop.save()
		self.assertEqual(loop.status, "Failed")
		loop = reload(loop)
		punch = frappe.get_doc("Punch Item", loop.punch_item)
		self.assertEqual(punch.category, "A")
		self.assertIn("XV-110", punch.title)

	def test_analog_loop_needs_a_span(self):
		package = make_package()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Loop Check", "package": package.name, "tag": "TT-1", "loop_type": "Analog Input"}
			).insert()

	# Punch items

	def test_punch_rules(self):
		package = make_package()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Punch Item",
					"package": package.name,
					"title": "Guard",
					"category": "A",
					"deferred": 1,
					"assigned_to": MNT,
					"due_on": add_days(nowdate(), 7),
				}
			).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Punch Item",
					"package": package.name,
					"title": "Label",
					"category": "B",
					"deferred": 1,
				}
			).insert()
		punch = frappe.get_doc(
			{"doctype": "Punch Item", "package": package.name, "title": "Guard", "category": "A"}
		).insert()
		self.assertEqual(punch.raised_by, "Administrator")
		punch.status = "Closed"
		with self.assertRaises(frappe.ValidationError):
			punch.save()
		# A refused save has already stamped the document, so work on a fresh copy.
		punch = reload(punch)
		punch.status = "Closed"
		punch.action_taken = "Guard fitted"
		punch.save()
		self.assertEqual(punch.verified_by, "Administrator")
		self.assertIsNotNone(punch.closed_on)
		punch = reload(punch)
		punch.status = "Open"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be reopened"):
			punch.save()

	# Readiness, acceptance and handover

	def test_full_flow_to_handover(self):
		package = make_package()
		self.assertEqual(package.status, "Planning")
		readiness = get_readiness(package.name)
		self.assertFalse(readiness["ready"])
		self.assertIn("Required Test", [b["kind"] for b in readiness["blockers"]])

		fat = pass_test(make_test(package.name, template=make_template().name, equipment_tag="FIL-201"))
		self.assertEqual(fat.status, "Passed")
		guard = frappe.get_doc(
			{"doctype": "Punch Item", "package": package.name, "title": "Guard", "category": "A"}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Punch Item",
				"package": package.name,
				"title": "Label",
				"category": "B",
				"deferred": 1,
				"assigned_to": MNT,
				"due_on": add_days(nowdate(), 14),
			}
		).insert()
		frappe.get_doc(
			{"doctype": "Punch Item", "package": package.name, "title": "Paint", "category": "C"}
		).insert()
		package = reload(package)
		self.assertEqual(package.status, "In Progress")
		self.assertEqual((package.open_punch_a, package.open_punch_b, package.open_punch_c), (1, 1, 1))

		package.operations_acceptor = OPS
		package.maintenance_acceptor = MNT
		package.save()
		with as_user(OPS), self.assertRaises(frappe.ValidationError):
			reload(package).accept("operations")

		guard.action_taken = "Guard fitted"
		guard.status = "Closed"
		guard.save()
		package = reload(package)
		self.assertEqual(package.status, "Ready for Handover", package.blockers)
		with self.assertRaises(frappe.ValidationError):
			package.hand_over()

		with as_user(MNT), self.assertRaises(frappe.PermissionError):
			reload(package).accept("operations")
		with as_user(OPS):
			reload(package).accept("operations")
		with as_user(MNT):
			reload(package).accept("maintenance")

		with extra_hooks(
			foames_commissioning_handed_over=[
				"foames.foames_commissioning.test_commissioning.record_handover"
			]
		):
			reload(package).hand_over()
		package = reload(package)
		self.assertEqual(package.status, "Handed Over")
		self.assertEqual(package.handed_over_by, "Administrator")
		self.assertEqual(HANDED_OVER, [package.name])
		self.assertEqual(frappe.db.get_value("Machine", "T-CM-FIL", "disabled"), 0)

		# Tests are frozen after handover; punch items may still be raised.
		with self.assertRaises(frappe.ValidationError):
			make_test(package.name, test_type="SAT")
		frappe.get_doc(
			{"doctype": "Punch Item", "package": package.name, "title": "Late find", "category": "C"}
		).insert()
		self.assertEqual(reload(package).status, "Handed Over")

		dossier = get_handover_dossier(package.name)
		self.assertEqual(len(dossier["tests"]), 1)
		self.assertEqual(len(dossier["tests"][0]["steps"]), 2)
		self.assertEqual(len(dossier["punch_items"]), 4)

	def test_changing_an_acceptor_clears_the_acceptance(self):
		package = make_package(operations_acceptor=OPS, maintenance_acceptor=MNT)
		pass_test(make_test(package.name, template=make_template().name))
		with as_user(OPS):
			reload(package).accept("operations")
		package = reload(package)
		self.assertIsNotNone(package.operations_accepted_on)
		package.operations_acceptor = MNT
		package.save()
		self.assertIsNone(package.operations_accepted_on)

	def test_readiness_hook_blocks_handover(self):
		package = make_package(operations_acceptor=OPS, maintenance_acceptor=MNT)
		pass_test(make_test(package.name, template=make_template().name))
		self.assertTrue(get_readiness(package.name)["ready"])
		with extra_hooks(
			foames_commissioning_readiness_checks=[
				"foames.foames_commissioning.test_commissioning.qualification_blocker"
			]
		):
			readiness = get_readiness(package.name)
		self.assertFalse(readiness["ready"])
		self.assertEqual(readiness["blockers"][0]["message"], "IQ protocol is not approved")

	def test_required_loop_checks(self):
		package = make_package(
			require_fat=0, require_loop_checks=1, operations_acceptor=OPS, maintenance_acceptor=MNT
		)
		self.assertIn("Loop Check", [b["reference"] for b in get_readiness(package.name)["blockers"]])

	def test_cancelled_package(self):
		package = make_package()
		package.cancelled = 1
		package.save()
		self.assertEqual(package.status, "Cancelled")
		with self.assertRaises(frappe.ValidationError):
			make_test(package.name)
		package.cancelled = 0
		package.save()
		self.assertEqual(package.status, "Planning")

	# Suggestions and reports

	def test_daily_suggestions(self):
		package = make_package(planned_handover=add_days(nowdate(), -3))
		punch = frappe.get_doc(
			{
				"doctype": "Punch Item",
				"package": package.name,
				"title": "Guard",
				"category": "A",
				"assigned_to": MNT,
				"due_on": add_days(nowdate(), -1),
			}
		).insert()
		created = check_commissioning()
		self.assertEqual(len(created), 2)
		self.assertEqual(check_commissioning(), [])
		punch_suggestion = frappe.get_all(
			"Agent Suggestion",
			filters={"reference_doctype": "Punch Item", "reference_name": punch.name},
			fields=["name", "severity", "category", "status"],
		)[0]
		self.assertEqual(
			(punch_suggestion.severity, punch_suggestion.category), ("Critical", "Commissioning")
		)
		punch.action_taken = "Guard fitted"
		punch.status = "Closed"
		punch.save()
		self.assertEqual(frappe.db.get_value("Agent Suggestion", punch_suggestion.name, "status"), "Done")

	def test_reports(self):
		package = make_package(planned_handover=add_days(nowdate(), -1))
		frappe.get_doc(
			{
				"doctype": "Punch Item",
				"package": package.name,
				"title": "Guard",
				"category": "A",
				"due_on": add_days(nowdate(), -2),
			}
		).insert()
		frappe.get_doc(
			{"doctype": "Punch Item", "package": package.name, "title": "Paint", "category": "C"}
		).insert()
		_columns, rows, _message, chart, summary = punch_list({"package": package.name})
		self.assertEqual([r["category"] for r in rows], ["A", "C"])
		self.assertEqual((rows[0]["blocks_handover"], rows[0]["overdue"]), (1, 1))
		self.assertEqual(rows[1]["blocks_handover"], 0)
		self.assertTrue(chart)
		self.assertEqual(next(s["value"] for s in summary if s["label"] == "Blocking Handover"), 1)
		self.assertEqual(punch_list({"package": package.name, "overdue_only": 1})[1][0]["title"], "Guard")
		_columns, rows, _message, _chart, _summary = commissioning_status({})
		row = next(r for r in rows if r["name"] == package.name)
		self.assertEqual((row["late"], row["open_punch_a"]), (1, 1))
		self.assertEqual(getdate(row["planned_handover"]), getdate(add_days(nowdate(), -1)))

	def test_workspace_references_exist(self):
		doc = frappe.get_doc("Workspace", "FoaMES Commissioning")
		for card in doc.number_cards:
			self.assertTrue(frappe.db.exists("Number Card", card.number_card_name), card.number_card_name)
		for shortcut in doc.shortcuts:
			self.assertTrue(frappe.db.exists(shortcut.type, shortcut.link_to), shortcut.link_to)
		for link in doc.links:
			if link.type == "Link":
				self.assertTrue(frappe.db.exists(link.link_type, link.link_to), link.link_to)
