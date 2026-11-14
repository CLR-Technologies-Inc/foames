# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Qualification rules and process capability. No Frappe site needed."""

import random
import statistics
import unittest
from datetime import date, datetime
from itertools import pairwise

from foames.foames_mes.spc import capability, d2
from foames.foames_validation import qualification as q


def readings(n=50, mean=10.0, sd=0.1, seed=7):
	rng = random.Random(seed)
	return [rng.gauss(mean, sd) for _ in range(n)]


class TestCapability(unittest.TestCase):
	def test_textbook_indices(self):
		values = [9.9, 10.1, 10.0, 9.8, 10.2, 10.0, 9.9, 10.1]
		cap = capability(values, lsl=9.0, usl=11.0)
		mean = statistics.fmean(values)
		mr_bar = statistics.fmean(abs(b - a) for a, b in pairwise(values))
		sigma_w = mr_bar / d2(2)
		self.assertAlmostEqual(cap["mean"], mean)
		self.assertAlmostEqual(cap["sigma_within"], sigma_w)
		self.assertAlmostEqual(cap["cp"], 2.0 / (6 * sigma_w))
		self.assertAlmostEqual(cap["cpk"], min(11.0 - mean, mean - 9.0) / (3 * sigma_w))
		self.assertAlmostEqual(cap["pp"], 2.0 / (6 * statistics.stdev(values)))
		self.assertEqual(cap["out_of_spec"], 0)

	def test_off_centre_process_has_lower_cpk_than_cp(self):
		cap = capability(readings(mean=10.5), lsl=9.0, usl=11.0)
		self.assertLess(cap["cpk"], cap["cp"])
		self.assertAlmostEqual(cap["cpk"], cap["cpu"])

	def test_one_sided_limit(self):
		cap = capability(readings(), usl=11.0)
		self.assertIsNone(cap["cp"])
		self.assertIsNone(cap["cpl"])
		self.assertAlmostEqual(cap["cpk"], cap["cpu"])

	def test_given_sigma_is_used_for_cp(self):
		cap = capability(readings(), lsl=9.0, usl=11.0, sigma_within=0.5)
		self.assertAlmostEqual(cap["cp"], 2.0 / 3.0)

	def test_no_spread_gives_no_index(self):
		cap = capability([10.0] * 10, lsl=9.0, usl=11.0)
		self.assertIsNone(cap["cpk"])
		self.assertIsNone(cap["ppk"])

	def test_bad_input(self):
		with self.assertRaises(ValueError):
			capability([1.0])
		with self.assertRaises(ValueError):
			capability([1.0, 2.0], lsl=5, usl=4)


class TestEvaluate(unittest.TestCase):
	def test_pass_fail(self):
		c = {"check_type": "Pass/Fail"}
		self.assertEqual(q.evaluate(c, {})["result"], q.PENDING)
		self.assertEqual(q.evaluate(c, {"passed": True})["result"], q.PASS)
		self.assertEqual(q.evaluate(c, {"passed": False})["result"], q.FAIL)

	def test_numeric_range_single_value(self):
		c = {"check_type": "Numeric Range", "lower_limit": 1, "upper_limit": 2}
		self.assertEqual(q.evaluate(c, {"value": 1.5})["result"], q.PASS)
		self.assertEqual(q.evaluate(c, {"value": 2})["result"], q.PASS)  # a limit is inside
		out = q.evaluate(c, {"value": 2.1})
		self.assertEqual(out["result"], q.FAIL)
		self.assertEqual(out["observed_value"], 2.1)
		self.assertEqual(q.evaluate(c, {})["result"], q.PENDING)

	def test_numeric_range_over_readings_reports_the_worst(self):
		c = {"check_type": "Numeric Range", "upper_limit": 80}
		out = q.evaluate(c, {"values": [70, 85, 79, 81]})
		self.assertEqual(out["result"], q.FAIL)
		self.assertEqual(out["observed_value"], 85)
		self.assertEqual(out["evidence"]["outside"], 2)
		self.assertIn("2 of 4", out["summary"])

	def test_numeric_range_needs_a_limit(self):
		with self.assertRaises(ValueError):
			q.evaluate({"check_type": "Numeric Range"}, {"value": 1})

	def test_capability_pass_and_fail(self):
		c = {"check_type": "Capability", "lower_limit": 9.0, "upper_limit": 11.0, "min_points": 30}
		good = q.evaluate(c, {"values": readings(sd=0.1)})
		self.assertEqual(good["result"], q.PASS)
		self.assertGreater(good["observed_value"], 1.33)
		self.assertEqual(good["evidence"]["index"], "Cpk")
		poor = q.evaluate(c, {"values": readings(sd=0.4)})
		self.assertEqual(poor["result"], q.FAIL)

	def test_capability_ppk_and_threshold(self):
		c = {
			"check_type": "Capability",
			"lower_limit": 9.0,
			"upper_limit": 11.0,
			"capability_index": "Ppk",
			"min_index": 1.67,
			"min_points": 30,
		}
		out = q.evaluate(c, {"values": readings(sd=0.25)})
		self.assertEqual(out["evidence"]["index"], "Ppk")
		self.assertLess(out["observed_value"], 1.67)
		self.assertEqual(out["result"], q.FAIL)

	def test_capability_fails_on_any_reading_out_of_spec(self):
		values = [*readings(sd=0.05), 11.5]
		c = {"check_type": "Capability", "lower_limit": 9.0, "upper_limit": 11.0, "min_index": 0.1}
		self.assertEqual(q.evaluate(c, {"values": values})["result"], q.FAIL)

	def test_too_few_readings_is_pending_not_pass(self):
		c = {"check_type": "Capability", "lower_limit": 9.0, "upper_limit": 11.0}
		out = q.evaluate(c, {"values": readings(n=10)})
		self.assertEqual(out["result"], q.PENDING)
		self.assertIn("at least 25", out["summary"])

	def test_statistical_control(self):
		c = {"check_type": "Statistical Control", "min_points": 25}
		stable = q.evaluate(c, {"values": readings(n=40, seed=3)})
		self.assertEqual(stable["result"], q.PASS, stable["summary"])
		shifted = readings(n=20, seed=3) + [v + 1.0 for v in readings(n=20, seed=4)]
		out = q.evaluate(c, {"values": shifted})
		self.assertEqual(out["result"], q.FAIL)
		self.assertGreater(out["observed_value"], 0)
		self.assertTrue(out["evidence"]["signals"])

	def test_unknown_check(self):
		with self.assertRaises(ValueError):
			q.evaluate({"check_type": "Vibes"}, {})


def row(result, critical=0, deviation="", disposition=None, criterion="c"):
	return {
		"criterion": criterion,
		"result": result,
		"critical": critical,
		"deviation": deviation,
		"disposition": disposition,
	}


class TestOutcome(unittest.TestCase):
	def test_all_pass(self):
		self.assertEqual(
			q.execution_outcome([row("Pass"), row("Pass")]), {"outcome": "Passed", "problems": []}
		)

	def test_empty_is_incomplete(self):
		self.assertEqual(q.execution_outcome([])["outcome"], q.INCOMPLETE)

	def test_pending_is_incomplete(self):
		out = q.execution_outcome([row("Pass"), row("Pending", criterion="Torque")])
		self.assertEqual(out["outcome"], q.INCOMPLETE)
		self.assertIn("Torque has no result yet", out["problems"])

	def test_failure_needs_deviation_and_disposition(self):
		out = q.execution_outcome([row("Fail")])
		self.assertEqual(out["outcome"], q.INCOMPLETE)
		self.assertEqual(len(out["problems"]), 2)

	def test_accepted_deviation(self):
		out = q.execution_outcome(
			[row("Pass"), row("Fail", deviation="DEV-1", disposition=q.ACCEPT_DEVIATION)]
		)
		self.assertEqual(out, {"outcome": q.PASSED_WITH_DEVIATIONS, "problems": []})

	def test_rejected_deviation_fails(self):
		out = q.execution_outcome([row("Fail", deviation="DEV-1", disposition=q.REJECT_DEVIATION)])
		self.assertEqual(out, {"outcome": q.FAILED, "problems": []})

	def test_critical_failure_cannot_be_accepted(self):
		out = q.execution_outcome(
			[row("Fail", critical=1, deviation="DEV-2", disposition=q.ACCEPT_DEVIATION)]
		)
		self.assertEqual(out["outcome"], q.FAILED)

	def test_not_applicable_needs_a_reason_and_not_on_critical(self):
		self.assertEqual(
			q.execution_outcome([row("Pass"), row("N/A", deviation="not fitted")])["outcome"], q.PASSED
		)
		self.assertEqual(q.execution_outcome([row("N/A")])["outcome"], q.INCOMPLETE)
		self.assertEqual(
			q.execution_outcome([row("N/A", critical=1, deviation="x")])["outcome"], q.INCOMPLETE
		)


def ex(name, outcome, approved, until=None, protocol="VP-1"):
	return {
		"name": name,
		"protocol": protocol,
		"outcome": outcome,
		"approved_on": approved,
		"qualified_until": until,
	}


class TestStatus(unittest.TestCase):
	TODAY = date(2026, 11, 14)

	def test_validity(self):
		self.assertEqual(q.qualified_until(date(2026, 1, 31), 1), date(2026, 2, 27))
		self.assertEqual(q.qualified_until(datetime(2026, 3, 15, 9), 12), date(2027, 3, 14))
		self.assertIsNone(q.qualified_until(date(2026, 3, 15), 0))
		self.assertEqual(q.add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
		self.assertEqual(q.add_months(date(2026, 11, 30), 3), date(2027, 2, 28))

	def test_none_is_not_qualified(self):
		self.assertEqual(q.qualification_status([], self.TODAY)["status"], q.NOT_QUALIFIED)

	def test_bands(self):
		def status(until):
			return q.qualification_status([ex("E1", "Passed", date(2026, 1, 1), until)], self.TODAY)

		self.assertEqual(status(None)["status"], q.QUALIFIED)
		self.assertEqual(status(date(2027, 6, 1))["status"], q.QUALIFIED)
		due = status(date(2026, 12, 1))
		self.assertEqual(due["status"], q.DUE_SOON)
		self.assertEqual(due["days_left"], 17)
		self.assertEqual(status(self.TODAY)["status"], q.DUE_SOON)
		self.assertEqual(status(date(2026, 11, 13))["status"], q.EXPIRED)

	def test_latest_failure_wins(self):
		out = q.qualification_status(
			[ex("E1", "Passed", date(2026, 1, 1)), ex("E2", "Failed", date(2026, 6, 1))], self.TODAY
		)
		self.assertEqual(out["status"], q.NOT_QUALIFIED)
		self.assertEqual(out["execution"], "E2")

	def test_consecutive_runs(self):
		runs = [
			ex("E1", "Passed", date(2026, 1, 1)),
			ex("E2", "Failed", date(2026, 1, 2)),
			ex("E3", "Passed", date(2026, 1, 3)),
			ex("E4", "Passed with Deviations", date(2026, 1, 4)),
		]
		out = q.qualification_status(runs, self.TODAY, required_runs=3)
		self.assertEqual(out["status"], q.RUNS_PENDING)
		self.assertEqual(out["runs_passed"], 2)
		runs.append(ex("E5", "Passed", date(2026, 1, 5)))
		self.assertEqual(q.qualification_status(runs, self.TODAY, required_runs=3)["status"], q.QUALIFIED)

	def test_runs_of_another_protocol_do_not_count(self):
		runs = [
			ex("E1", "Passed", date(2026, 1, 1), protocol="VP-OLD"),
			ex("E2", "Passed", date(2026, 1, 2), protocol="VP-NEW"),
		]
		self.assertEqual(q.qualification_status(runs, self.TODAY, required_runs=2)["status"], q.RUNS_PENDING)

	def test_prerequisites(self):
		self.assertIsNone(q.prerequisite_problem("IQ", None))
		self.assertIsNone(q.prerequisite_problem("OQ", {"status": q.DUE_SOON}))
		problem = q.prerequisite_problem("OQ", {"status": q.EXPIRED})
		self.assertIn("Installation Qualification (IQ) is Expired", problem)
		self.assertEqual(q.protocol_type("PPQ")["default_runs"], 3)
		with self.assertRaises(ValueError):
			q.protocol_type("XQ")


class TestFindings(unittest.TestCase):
	def test_due_and_expired_become_suggestions(self):
		base = {
			"subject_type": "Machine",
			"subject": "PRESS-1",
			"protocol_type": "OQ",
			"protocol": "VP-0001",
			"execution": "VE-0001",
		}
		rows = [
			{**base, "status": q.QUALIFIED, "qualified_until": date(2027, 1, 1), "days_left": 48},
			{**base, "status": q.DUE_SOON, "qualified_until": date(2026, 12, 1), "days_left": 17},
			{
				**base,
				"subject": "PRESS-2",
				"status": q.EXPIRED,
				"qualified_until": date(2026, 11, 1),
				"days_left": -13,
			},
		]
		out = q.findings(rows)
		self.assertEqual(len(out), 2)
		self.assertEqual(out[0]["rule_key"], "validation:Machine:PRESS-1:OQ")
		self.assertEqual(out[0]["severity"], "Warning")
		self.assertEqual(out[1]["severity"], "Critical")
		self.assertEqual(out[1]["reference_doctype"], "Validation Protocol")
		self.assertEqual(out[1]["evidence"]["qualified_until"], "2026-11-01")
		self.assertIn("expired", out[1]["title"])


if __name__ == "__main__":
	unittest.main()
