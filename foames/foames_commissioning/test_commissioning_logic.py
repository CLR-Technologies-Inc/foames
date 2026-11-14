# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Commissioning rules: test steps, the test sequence, loop checks, punch items, readiness and the
suggestions. No Frappe site needed."""

import unittest
from datetime import date, datetime

from foames.foames_commissioning.commissioning import (
	default_points,
	evaluate_analog_point,
	evaluate_digital_point,
	evaluate_step,
	expected_value,
	findings,
	is_past,
	loop_status,
	package_status,
	percent_complete,
	punch_blocks_handover,
	punch_deferral_problem,
	readiness,
	sequence_blockers,
	span_error_percent,
	status_of_test,
)

NOW = datetime(2026, 11, 14, 12, 0, 0)


class TestSteps(unittest.TestCase):
	def test_value_step_within_and_outside_limits(self):
		self.assertEqual(evaluate_step("Value", "5.0", "4", "6"), "Pass")
		self.assertEqual(evaluate_step("Value", "4", "4", "6"), "Pass")
		self.assertEqual(evaluate_step("Value", "6", "4", "6"), "Pass")
		self.assertEqual(evaluate_step("Value", "3.99", "4", "6"), "Fail")
		self.assertEqual(evaluate_step("Value", "6.01", "4", "6"), "Fail")

	def test_open_limits(self):
		self.assertEqual(evaluate_step("Value", "1000", "4", ""), "Pass")
		self.assertEqual(evaluate_step("Value", "-1000", None, "6"), "Pass")
		self.assertEqual(evaluate_step("Value", "0", "0", None), "Pass")
		self.assertEqual(evaluate_step("Value", "-0.1", "0", None), "Fail")

	def test_value_step_without_reading_is_pending(self):
		self.assertEqual(evaluate_step("Value", None, "4", "6"), "Pending")
		self.assertEqual(evaluate_step("Value", "", "4", "6", result="Pass"), "Pending")

	def test_value_step_ignores_a_typed_result(self):
		self.assertEqual(evaluate_step("Value", "10", "4", "6", result="Pass"), "Fail")

	def test_check_and_text_keep_the_testers_result(self):
		self.assertEqual(evaluate_step("Check", result="Pass"), "Pass")
		self.assertEqual(evaluate_step("Text", result="Fail"), "Fail")
		self.assertEqual(evaluate_step("Check"), "Pending")
		self.assertEqual(evaluate_step("Check", result="Maybe"), "Pending")

	def test_not_applicable_is_kept_for_every_kind(self):
		self.assertEqual(evaluate_step("Value", "10", "4", "6", result="N/A"), "N/A")
		self.assertEqual(evaluate_step("Check", result="N/A"), "N/A")


class TestTestStatus(unittest.TestCase):
	def test_progression(self):
		self.assertEqual(status_of_test([]), "Not Started")
		self.assertEqual(status_of_test(["Pending", "Pending"]), "Not Started")
		self.assertEqual(status_of_test(["Pass", "Pending"]), "In Progress")
		self.assertEqual(status_of_test(["Pass", "N/A"]), "Awaiting Sign-off")
		self.assertEqual(status_of_test(["Pass", "N/A"], performed_by="tech@example.com"), "Passed")

	def test_a_failure_fails_at_once(self):
		self.assertEqual(status_of_test(["Fail", "Pending"]), "Failed")
		self.assertEqual(status_of_test(["Pass", "Fail"], performed_by="x"), "Failed")

	def test_witness(self):
		self.assertEqual(
			status_of_test(["Pass"], performed_by="x", witness_required=True), "Awaiting Sign-off"
		)
		self.assertEqual(
			status_of_test(["Pass"], performed_by="x", witness_required=True, witnessed_by="Customer QA"),
			"Passed",
		)

	def test_all_not_applicable_does_not_pass(self):
		self.assertEqual(status_of_test(["N/A", "N/A"], performed_by="x"), "In Progress")

	def test_cancelled(self):
		self.assertEqual(status_of_test(["Fail"], cancelled=True), "Cancelled")


class TestSequence(unittest.TestCase):
	def test_sat_waits_for_fat_and_mechanical_completion(self):
		earlier = [
			{"name": "T1", "test_type": "FAT", "status": "Passed"},
			{"name": "T2", "test_type": "Mechanical Completion", "status": "In Progress"},
		]
		self.assertEqual([b["name"] for b in sequence_blockers("SAT", earlier)], ["T2"])

	def test_later_and_same_stage_tests_do_not_block(self):
		others = [
			{"name": "T1", "test_type": "Performance Test", "status": "Failed"},
			{"name": "T2", "test_type": "SAT", "status": "Failed"},
		]
		self.assertEqual(sequence_blockers("Functional Test", others), [])
		self.assertEqual(sequence_blockers("FAT", others), [])

	def test_cancelled_tests_are_ignored(self):
		self.assertEqual(
			sequence_blockers("SAT", [{"name": "T1", "test_type": "FAT", "status": "Cancelled"}]), []
		)


class TestLoopChecks(unittest.TestCase):
	def test_default_points(self):
		self.assertEqual([p["percent_of_span"] for p in default_points("Analog Input")], [0, 25, 50, 75, 100])
		self.assertEqual([p["expected_state"] for p in default_points("Digital Output")], ["On", "Off"])

	def test_expected_value_and_span_error(self):
		self.assertEqual(expected_value(4, 20, 50), 12)
		self.assertEqual(expected_value(-50, 150, 25), 0)
		self.assertAlmostEqual(span_error_percent(12.16, 12, 4, 20), 1.0)
		with self.assertRaises(ValueError):
			span_error_percent(1, 1, 5, 5)

	def test_analog_point(self):
		ok = evaluate_analog_point(50, 0, 200, 1, as_found="101")
		self.assertEqual((ok["expected"], ok["result"]), (100.0, "Pass"))
		self.assertAlmostEqual(ok["error_percent"], 0.5)
		self.assertEqual(evaluate_analog_point(50, 0, 200, 1, as_found="102")["result"], "Pass")
		self.assertEqual(evaluate_analog_point(50, 0, 200, 1, as_found="102.5")["result"], "Fail")

	def test_as_left_decides_after_adjustment(self):
		point = evaluate_analog_point(100, 0, 10, 0.5, as_found="10.4", as_left="10.02")
		self.assertEqual(point["result"], "Pass")
		self.assertAlmostEqual(point["error_percent"], 0.2)

	def test_default_tolerance_and_pending(self):
		self.assertEqual(evaluate_analog_point(0, 0, 100, None, as_found="1")["result"], "Pass")
		self.assertEqual(evaluate_analog_point(0, 0, 100, None, as_found="1.1")["result"], "Fail")
		pending = evaluate_analog_point(0, 0, 100, 1)
		self.assertEqual((pending["result"], pending["error_percent"]), ("Pending", None))

	def test_reversed_range(self):
		# A level transmitter calibrated high to low still has its span as a positive number.
		point = evaluate_analog_point(25, 100, 0, 1, as_found="75.5")
		self.assertEqual(point["expected"], 75)
		self.assertEqual(point["result"], "Pass")

	def test_digital_point(self):
		self.assertEqual(evaluate_digital_point("On", "On"), "Pass")
		self.assertEqual(evaluate_digital_point("On", "Off"), "Fail")
		self.assertEqual(evaluate_digital_point("On", None), "Pending")

	def test_loop_status(self):
		self.assertEqual(loop_status([]), "Not Started")
		self.assertEqual(loop_status(["Pending"] * 5), "Not Started")
		self.assertEqual(loop_status(["Pass", "Pending"]), "In Progress")
		self.assertEqual(loop_status(["Pass", "Pass"]), "In Progress")
		self.assertEqual(loop_status(["Pass", "Pass"], checked_by="tech"), "Passed")
		self.assertEqual(loop_status(["Pass", "Fail", "Pending"], checked_by="tech"), "Failed")
		self.assertEqual(loop_status(["Fail"], cancelled=True), "Cancelled")


class TestPunch(unittest.TestCase):
	def test_categories(self):
		self.assertTrue(punch_blocks_handover({"category": "A", "status": "Open"}))
		self.assertTrue(
			punch_blocks_handover({"category": "A", "status": "Ready for Verification", "deferred": 1})
		)
		self.assertTrue(punch_blocks_handover({"category": "B", "status": "Open"}))
		self.assertFalse(
			punch_blocks_handover(
				{
					"category": "B",
					"status": "Open",
					"deferred": 1,
					"assigned_to": "m@x",
					"due_on": date(2026, 12, 1),
				}
			)
		)
		self.assertTrue(
			punch_blocks_handover({"category": "B", "status": "Open", "deferred": 1, "assigned_to": "m@x"})
		)
		self.assertFalse(punch_blocks_handover({"category": "C", "status": "Open"}))
		self.assertFalse(punch_blocks_handover({"category": "A", "status": "Closed"}))
		self.assertFalse(punch_blocks_handover({"category": "A", "status": "Cancelled"}))

	def test_deferral_rules(self):
		self.assertIsNone(punch_deferral_problem("A", False, None, None))
		self.assertIn("cannot be deferred", punch_deferral_problem("A", True, "m@x", date(2026, 12, 1)))
		self.assertIn("owner and a due date", punch_deferral_problem("B", True, None, date(2026, 12, 1)))
		self.assertIsNone(punch_deferral_problem("B", True, "m@x", date(2026, 12, 1)))
		self.assertIsNone(punch_deferral_problem("C", True, "m@x", date(2026, 12, 1)))


def ready_package(**overrides):
	values = {
		"items": [{"tag": "FIL-201"}],
		"required_test_types": ["FAT", "SAT"],
		"tests": [
			{"name": "T1", "test_type": "FAT", "status": "Passed"},
			{"name": "T2", "test_type": "SAT", "status": "Passed"},
		],
		"loop_checks": [{"name": "L1", "tag": "PT-101", "status": "Passed"}],
		"punch_items": [{"name": "P1", "category": "C", "status": "Open", "description": "Paint scratch"}],
		"operations_acceptor": "ops@example.com",
		"maintenance_acceptor": "mnt@example.com",
	}
	values.update(overrides)
	return values


class TestReadiness(unittest.TestCase):
	def test_ready(self):
		result = readiness(ready_package())
		self.assertTrue(result["ready"], result["blockers"])
		self.assertEqual(result["progress"]["tests_passed"], 2)
		self.assertEqual(result["progress"]["punch_open_by_category"], {"A": 0, "B": 0, "C": 1})
		self.assertAlmostEqual(result["progress"]["percent_complete"], 75.0)

	def test_each_blocker(self):
		result = readiness(
			ready_package(
				items=[],
				required_test_types=["FAT", "SAT", "Performance Test"],
				tests=[
					{"name": "T1", "test_type": "FAT", "status": "Passed"},
					{"name": "T2", "test_type": "SAT", "status": "Failed"},
					{"name": "T3", "test_type": "SAT", "status": "Cancelled"},
				],
				loop_checks=[{"name": "L1", "tag": "PT-101", "status": "In Progress"}],
				punch_items=[
					{"name": "P1", "category": "A", "status": "Open", "description": "Guard missing"},
					{"name": "P2", "category": "B", "status": "Open"},
					{"name": "P3", "category": "A", "status": "Closed"},
				],
				operations_acceptor=None,
				maintenance_acceptor=None,
				extra_blockers=[
					{"kind": "Qualification", "reference": None, "message": "IQ protocol not approved"}
				],
			)
		)
		self.assertFalse(result["ready"])
		kinds = [b["kind"] for b in result["blockers"]]
		self.assertEqual(
			kinds,
			[
				"Scope",
				"Required Test",
				"Required Test",
				"Test",
				"Loop Check",
				"Punch Item",
				"Punch Item",
				"Acceptance",
				"Acceptance",
				"Qualification",
			],
		)
		refs = [b["reference"] for b in result["blockers"]]
		self.assertIn("SAT", refs)
		self.assertIn("Performance Test", refs)
		self.assertNotIn("T3", refs)
		self.assertIn("Guard missing", result["blockers"][5]["message"])
		self.assertTrue(result["blockers"][6]["message"].endswith("is open"))

	def test_deferred_b_does_not_block(self):
		deferred = {
			"name": "P2",
			"category": "B",
			"status": "Open",
			"deferred": 1,
			"assigned_to": "m@x",
			"due_on": date(2026, 12, 1),
		}
		self.assertTrue(readiness(ready_package(punch_items=[deferred]))["ready"])

	def test_percent_complete(self):
		self.assertEqual(percent_complete([], [], []), 0.0)
		self.assertAlmostEqual(
			percent_complete(
				[{"status": "Passed"}, {"status": "Failed"}],
				[],
				[{"status": "Closed"}, {"status": "Cancelled"}],
			),
			200 / 3,
		)

	def test_package_status(self):
		self.assertEqual(package_status("Planning", False, False), "Planning")
		self.assertEqual(package_status("Planning", True, False), "In Progress")
		self.assertEqual(package_status("In Progress", True, True), "Ready for Handover")
		self.assertEqual(package_status("Ready for Handover", True, False), "In Progress")
		self.assertEqual(package_status("Handed Over", True, False), "Handed Over")
		self.assertEqual(package_status("Cancelled", True, True), "Cancelled")


class TestFindings(unittest.TestCase):
	def test_is_past(self):
		self.assertTrue(is_past(date(2026, 11, 13), NOW))
		self.assertFalse(is_past(date(2026, 11, 14), NOW))
		self.assertTrue(is_past(datetime(2026, 11, 14, 11, 0), NOW))
		self.assertFalse(is_past(None, NOW))

	def test_overdue_punch_items(self):
		punch = [
			{
				"name": "P1",
				"package": "CPK-1",
				"category": "A",
				"status": "Open",
				"due_on": date(2026, 11, 10),
			},
			{
				"name": "P2",
				"package": "CPK-1",
				"category": "C",
				"status": "Ready for Verification",
				"due_on": date(2026, 11, 1),
				"assigned_to": "m@x",
			},
			{
				"name": "P3",
				"package": "CPK-1",
				"category": "B",
				"status": "Open",
				"due_on": date(2026, 11, 20),
			},
			{
				"name": "P4",
				"package": "CPK-1",
				"category": "A",
				"status": "Closed",
				"due_on": date(2026, 11, 1),
			},
			{"name": "P5", "package": "CPK-1", "category": "A", "status": "Open", "due_on": None},
		]
		out = findings(punch, [], NOW)
		self.assertEqual([f["reference_name"] for f in out], ["P1", "P2"])
		self.assertEqual([f["severity"] for f in out], ["Critical", "Info"])
		self.assertEqual(out[0]["rule_key"], "commissioning:punch:P1:2026-11-10")
		self.assertEqual(out[0]["category"], "Commissioning")
		self.assertIn("assigned to nobody", out[0]["suggestion"])
		self.assertIn("assigned to m@x", out[1]["suggestion"])

	def test_late_packages(self):
		packages = [
			{
				"name": "CPK-1",
				"title": "Filler",
				"status": "In Progress",
				"planned_handover": date(2026, 11, 1),
				"blockers": 3,
			},
			{"name": "CPK-2", "status": "Handed Over", "planned_handover": date(2026, 11, 1)},
			{"name": "CPK-3", "status": "Planning", "planned_handover": date(2026, 12, 1)},
		]
		out = findings([], packages, NOW)
		self.assertEqual(len(out), 1)
		self.assertEqual(out[0]["reference_doctype"], "Commissioning Package")
		self.assertIn("3 open blockers", out[0]["suggestion"])
		self.assertIn("Filler", out[0]["title"])


if __name__ == "__main__":
	unittest.main()
