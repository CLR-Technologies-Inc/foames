# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""PFMEA arithmetic: the AIAG-VDA action priority table, RPN, observed occurrence and the
suggestions. No Frappe site needed."""

import unittest
from datetime import date

from foames.foames_mes.pfmea import (
	action_priority,
	check_item,
	check_release,
	findings,
	occurrence_from_rate,
	per_thousand,
	rate_for_occurrence,
	rpn,
	summarize,
	valid_rating,
)

# The AIAG-VDA FMEA Handbook (2019) action priority table, written out row by row: severity band,
# occurrence band, then the priority for detection 7-10, 5-6, 2-4 and 1.
TABLE = [
	((9, 10), (8, 10), "HHHH"),
	((9, 10), (6, 7), "HHHH"),
	((9, 10), (4, 5), "HHHM"),
	((9, 10), (2, 3), "HMLL"),
	((9, 10), (1, 1), "LLLL"),
	((7, 8), (8, 10), "HHHH"),
	((7, 8), (6, 7), "HHHM"),
	((7, 8), (4, 5), "HMMM"),
	((7, 8), (2, 3), "MMLL"),
	((7, 8), (1, 1), "LLLL"),
	((4, 6), (8, 10), "HHMM"),
	((4, 6), (6, 7), "MMML"),
	((4, 6), (4, 5), "MLLL"),
	((4, 6), (2, 3), "LLLL"),
	((4, 6), (1, 1), "LLLL"),
	((2, 3), (8, 10), "MMLL"),
	((2, 3), (6, 7), "LLLL"),
	((2, 3), (4, 5), "LLLL"),
	((2, 3), (2, 3), "LLLL"),
	((2, 3), (1, 1), "LLLL"),
	((1, 1), (1, 10), "LLLL"),
]
D_BANDS = ((7, 10), (5, 6), (2, 4), (1, 1))


class TestActionPriority(unittest.TestCase):
	def test_every_combination_matches_the_handbook_table(self):
		checked = 0
		for (s_low, s_high), (o_low, o_high), priorities in TABLE:
			for s in range(s_low, s_high + 1):
				for o in range(o_low, o_high + 1):
					for (d_low, d_high), expected in zip(D_BANDS, priorities, strict=True):
						for d in range(d_low, d_high + 1):
							self.assertEqual(action_priority(s, o, d), expected, (s, o, d))
							checked += 1
		self.assertEqual(checked, 1000)

	def test_severity_outranks_the_product(self):
		# RPN ranks 3x10x10=300 above 9x3x7=189; the AP table ranks the first Medium and the
		# second, with its severity 9 effect, High.
		self.assertEqual(action_priority(3, 10, 10), "M")
		self.assertEqual(action_priority(9, 3, 5), "M")
		self.assertEqual(action_priority(9, 3, 7), "H")
		self.assertGreater(rpn(3, 10, 10), rpn(9, 3, 7))

	def test_missing_or_bad_ratings_give_no_priority(self):
		self.assertIsNone(action_priority(None, 5, 5))
		self.assertIsNone(action_priority(0, 5, 5))
		self.assertIsNone(action_priority(11, 5, 5))
		self.assertIsNone(action_priority(5.5, 5, 5))
		self.assertIsNone(rpn(5, None, 5))
		self.assertEqual(action_priority("8", "6", "1"), "M")
		self.assertTrue(valid_rating(7.0))
		self.assertFalse(valid_rating("x"))

	def test_rpn(self):
		self.assertEqual(rpn(10, 10, 10), 1000)
		self.assertEqual(rpn(7, 4, 3), 84)


class TestObservedOccurrence(unittest.TestCase):
	def test_rate_bands(self):
		cases = [
			(150, 10),
			(100, 10),
			(60, 9),
			(20, 8),
			(10, 7),
			(9.99, 6),
			(2, 6),
			(0.5, 5),
			(0.1, 4),
			(0.05, 3),
			(0.01, 3),
			(0.009, 2),
			(0, 2),
		]
		for rate, expected in cases:
			self.assertEqual(occurrence_from_rate(rate), expected, rate)
		self.assertIsNone(occurrence_from_rate(None))

	def test_per_thousand(self):
		self.assertAlmostEqual(per_thousand(3, 1500), 2.0)
		self.assertIsNone(per_thousand(3, 0))
		self.assertEqual(per_thousand(None, 100), 0.0)

	def test_band_floor(self):
		self.assertEqual(rate_for_occurrence(6), 2.0)
		self.assertIsNone(rate_for_occurrence(1))


class TestChecks(unittest.TestCase):
	def test_draft_rows_may_leave_ratings_empty(self):
		self.assertEqual(check_item({"severity": 8}), [])
		self.assertTrue(check_item({"severity": 12}))

	def test_completed_action_needs_rerating_and_date(self):
		row = {"severity": 8, "occurrence": 6, "detection": 6, "prevention_action": "Poka-yoke the fixture"}
		self.assertEqual(len(check_item({**row, "action_status": "Completed"})), 2)
		done = {**row, "action_status": "Completed", "completion_date": "2026-11-01"}
		done.update(new_severity=8, new_occurrence=2, new_detection=6)
		self.assertEqual(check_item(done), [])

	def test_not_implemented_needs_a_reason_and_status_needs_an_action(self):
		row = {"prevention_action": "Add a sensor", "action_status": "Not Implemented"}
		self.assertEqual(check_item(row), ["Record why the action was not implemented"])
		self.assertEqual(
			check_item({"action_status": "Open"}), ["An action status needs a prevention or detection action"]
		)

	def test_release_needs_every_rating(self):
		self.assertTrue(check_release([]))
		problems = check_release([{"severity": 8, "occurrence": 4, "detection": 3}, {"severity": 5}])
		self.assertEqual(problems, ["Row 2 needs occurrence, detection"])

	def test_summary(self):
		items = [
			{"action_priority": "H", "prevention_action": "x", "action_status": "Open"},
			{"action_priority": "H", "detection_action": "y", "action_status": "Completed"},
			{"action_priority": "M"},
			{"action_priority": "L"},
			{},
		]
		self.assertEqual(summarize(items), {"high": 2, "medium": 1, "low": 1, "open_actions": 1})


PFMEA = {"name": "PFMEA-00001", "title": "Housing line"}


def item(**overrides):
	values = {
		"row": "abc123",
		"idx": 1,
		"op_no": "20",
		"process_step": "Press fit bearing",
		"failure_mode": "Bearing not seated",
		"machine": "PRESS-1",
		"severity": 8,
		"occurrence": 3,
		"detection": 4,
		"action_priority": "M",
	}
	values.update(overrides)
	return values


class TestFindings(unittest.TestCase):
	def test_nothing_for_a_quiet_row(self):
		self.assertEqual(findings(PFMEA, [item()], date(2026, 11, 14)), [])

	def test_observed_occurrence_above_rating(self):
		row = item(
			observed_occurrence=6,
			observed_per_thousand=2.5,
			observed_incidents=5,
			observed_units=2000,
		)
		(finding,) = findings(PFMEA, [row], date(2026, 11, 14))
		self.assertEqual(finding["rule_key"], "pfmea:PFMEA-00001:abc123:occurrence:6")
		# S8 O6 D4 is High.
		self.assertEqual(finding["severity"], "Critical")
		self.assertEqual(finding["evidence"]["action_priority_at_observed"], "H")
		self.assertEqual(finding["reference_doctype"], "PFMEA")
		self.assertIn("supports occurrence 6", finding["suggestion"])
		# At or below the rating, nothing.
		self.assertEqual(findings(PFMEA, [item(observed_occurrence=3)], date(2026, 11, 14)), [])

	def test_spc_signals(self):
		row = item(spc_signals=2, measurement_name="press_force", latest_signal_at="2026-11-14 08:00:00")
		(finding,) = findings(PFMEA, [row], date(2026, 11, 14))
		self.assertEqual(finding["rule_key"], "pfmea:PFMEA-00001:abc123:spc")
		self.assertEqual(finding["severity"], "Warning")
		self.assertEqual(
			findings(PFMEA, [{**row, "severity": 9}], date(2026, 11, 14))[0]["severity"], "Critical"
		)

	def test_high_priority_without_action(self):
		row = item(severity=9, occurrence=6, detection=5, action_priority="H")
		(finding,) = findings(PFMEA, [row], date(2026, 11, 14))
		self.assertTrue(finding["rule_key"].endswith(":high-without-action"))
		with_action = {**row, "prevention_action": "Error-proof the nest"}
		self.assertEqual(findings(PFMEA, [with_action], date(2026, 11, 14)), [])
		justified = {**row, "action_status": "Not Implemented", "action_taken": "Customer accepts"}
		self.assertEqual(findings(PFMEA, [justified], date(2026, 11, 14)), [])

	def test_overdue_action(self):
		row = item(detection_action="Add force monitoring", target_date="2026-11-01", action_status="Open")
		(finding,) = findings(PFMEA, [row], date(2026, 11, 14))
		self.assertEqual(finding["rule_key"], "pfmea:PFMEA-00001:abc123:overdue:2026-11-01")
		self.assertEqual(findings(PFMEA, [{**row, "action_status": "Completed"}], date(2026, 11, 14)), [])
		self.assertEqual(findings(PFMEA, [row], date(2026, 11, 1)), [])
		self.assertEqual(
			findings(PFMEA, [{**row, "target_date": date(2026, 10, 1)}], date(2026, 11, 14))[0]["evidence"][
				"target_date"
			],
			"2026-10-01",
		)


if __name__ == "__main__":
	unittest.main()
