# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import unittest

from foames.foames_mes.oee import TimeLedger, compute_oee, ledger_from_states
from foames.foames_mes.suggestions import all_rules, dominant_downtime_reason, silent_machines


class TestOEE(unittest.TestCase):
	def test_textbook_oee(self):
		ledger = TimeLedger(planned_minutes=480, run_minutes=400, unplanned_downtime_minutes=80)
		# 400 min at 60 s ideal cycle is 400 units at rated speed; 360 made, 342 good.
		result = compute_oee(ledger, good_count=342, scrap_count=18, ideal_cycle_seconds=60)
		self.assertAlmostEqual(result.availability, 400 / 480)
		self.assertAlmostEqual(result.performance, 0.9)
		self.assertAlmostEqual(result.quality, 0.95)
		self.assertAlmostEqual(result.oee, (400 / 480) * 0.9 * 0.95)

	def test_planned_downtime_is_excluded_from_availability(self):
		ledger = TimeLedger(planned_minutes=480, run_minutes=400, planned_downtime_minutes=80)
		self.assertAlmostEqual(compute_oee(ledger, 10, 0, 60).availability, 1.0)

	def test_unknown_time_is_loss_not_run_time(self):
		ledger = ledger_from_states([(200, "Running", False)], planned_minutes=480)
		self.assertAlmostEqual(ledger.unknown_minutes, 280)
		self.assertAlmostEqual(ledger.coverage, 200 / 480)
		result = compute_oee(ledger, 200, 0, 60)
		self.assertAlmostEqual(result.availability, 200 / 480)
		self.assertTrue(any("without a machine signal" in n for n in result.notes))

	def test_performance_is_capped_and_flagged(self):
		ledger = TimeLedger(planned_minutes=60, run_minutes=60)
		result = compute_oee(ledger, 100, 0, ideal_cycle_seconds=60)
		self.assertEqual(result.performance, 1.0)
		self.assertTrue(any("above 100" in n for n in result.notes))

	def test_no_cycle_time_assumes_full_performance(self):
		result = compute_oee(TimeLedger(60, run_minutes=60), 10, 0, None)
		self.assertEqual(result.performance, 1.0)
		self.assertTrue(result.notes)

	def test_ledger_from_states(self):
		ledger = ledger_from_states(
			[
				(100, "Running", False),
				(20, "Down", True),
				(30, "Down", False),
				(10, "Idle", False),
				(5, "Setup", False),
			],
			165,
		)
		self.assertEqual(
			(ledger.run_minutes, ledger.planned_downtime_minutes, ledger.unplanned_downtime_minutes),
			(100, 20, 30),
		)
		self.assertEqual(ledger.unknown_minutes, 0)
		self.assertEqual(ledger.coverage, 1.0)


class TestSuggestionRules(unittest.TestCase):
	def test_silent_and_stalled(self):
		snap = {
			"machines": [
				{"name": "M1", "status": "Unknown", "minutes_since_count": 45, "last_seen": "x"},
				{"name": "M2", "status": "Running", "minutes_since_count": 45, "last_seen": "y"},
				{"name": "M3", "status": "Running", "minutes_since_count": 5},
				{"name": "M4", "status": "Unknown", "minutes_since_count": None},
			]
		}
		found = silent_machines(snap)
		self.assertEqual([f["reference_name"] for f in found], ["M1", "M2"])
		self.assertEqual([f["rule_key"] for f in found], ["silent:M1:x", "stalled:M2:y"])

	def test_dominant_downtime(self):
		snap = {
			"downtime_by_machine": [
				{
					"machine": "M1",
					"period": "last 1 day(s)",
					"total_minutes": 100,
					"top_reason": "CHANGEOVER",
					"top_minutes": 70,
				}
			]
		}
		found = dominant_downtime_reason(snap)
		self.assertEqual(found[0]["category"], "Downtime")
		self.assertIn("70%", found[0]["title"])
		# The window is part of the key, so a new window raises the finding again after it was resolved.
		self.assertEqual(found[0]["rule_key"], "downtime:M1:CHANGEOVER:last 1 day(s)")
		snap["downtime_by_machine"][0]["period"] = "2026-10-30 to 2026-10-31"
		self.assertNotEqual(dominant_downtime_reason(snap)[0]["rule_key"], found[0]["rule_key"])

	def test_all_rules_on_empty_snapshot(self):
		self.assertEqual(all_rules({}), [])
