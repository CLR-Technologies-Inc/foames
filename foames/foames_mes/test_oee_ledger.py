# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Edge cases of the OEE arithmetic and the time ledger. No Frappe site needed."""

import random
import unittest

from foames.foames_mes.oee import OEEResult, TimeLedger, compute_oee, ledger_from_states


class TestTimeLedger(unittest.TestCase):
	def test_accounted_minutes_sums_every_bucket(self):
		ledger = TimeLedger(
			planned_minutes=100,
			run_minutes=10,
			planned_downtime_minutes=20,
			unplanned_downtime_minutes=30,
			idle_minutes=5,
			setup_minutes=15,
			unknown_minutes=20,
		)
		self.assertEqual(ledger.accounted_minutes, 100)

	def test_coverage_excludes_unknown_time(self):
		ledger = TimeLedger(planned_minutes=100, run_minutes=60, unknown_minutes=40)
		self.assertAlmostEqual(ledger.coverage, 0.6)

	def test_coverage_is_zero_without_planned_time(self):
		self.assertEqual(TimeLedger(planned_minutes=0, run_minutes=10).coverage, 0.0)
		self.assertEqual(TimeLedger(planned_minutes=-5, run_minutes=10).coverage, 0.0)

	def test_coverage_is_clamped_when_intervals_exceed_the_plan(self):
		ledger = TimeLedger(planned_minutes=100, run_minutes=150)
		self.assertEqual(ledger.coverage, 1.0)

	def test_ledger_from_states_fills_gaps_with_unknown(self):
		ledger = ledger_from_states([(30, "Running", False), (10, "Idle", False)], planned_minutes=60)
		self.assertEqual(ledger.unknown_minutes, 20)
		self.assertAlmostEqual(ledger.coverage, 40 / 60)

	def test_ledger_from_states_keeps_explicit_unknown(self):
		ledger = ledger_from_states([(15, "Unknown", False), (45, "Running", False)], planned_minutes=60)
		self.assertEqual(ledger.unknown_minutes, 15)
		self.assertEqual(ledger.run_minutes, 45)

	def test_ledger_from_states_treats_unrecognised_states_as_unknown(self):
		ledger = ledger_from_states([(60, "Purple", False)], planned_minutes=60)
		self.assertEqual(ledger.unknown_minutes, 60)
		self.assertEqual(ledger.coverage, 0.0)

	def test_ledger_from_states_does_not_shrink_over_coverage(self):
		# Intervals longer than the plan are kept as they are; nothing becomes negative.
		ledger = ledger_from_states([(90, "Running", False)], planned_minutes=60)
		self.assertEqual(ledger.run_minutes, 90)
		self.assertEqual(ledger.unknown_minutes, 0)

	def test_ledger_from_states_ignores_planned_flag_outside_down(self):
		ledger = ledger_from_states([(10, "Running", True), (10, "Idle", True), (10, "Setup", True)], 30)
		self.assertEqual(ledger.planned_downtime_minutes, 0)
		self.assertEqual((ledger.run_minutes, ledger.idle_minutes, ledger.setup_minutes), (10, 10, 10))

	def test_ledger_from_states_with_no_intervals(self):
		ledger = ledger_from_states([], planned_minutes=480)
		self.assertEqual(ledger.unknown_minutes, 480)
		self.assertEqual(ledger.coverage, 0.0)

	def test_tiny_float_gap_is_not_counted(self):
		ledger = ledger_from_states([(0.1, "Running", False)] * 3, planned_minutes=0.3)
		self.assertAlmostEqual(ledger.unknown_minutes, 0.0)


class TestComputeOEE(unittest.TestCase):
	def test_result_carries_inputs(self):
		ledger = TimeLedger(planned_minutes=60, run_minutes=60)
		result = compute_oee(ledger, 50, 5, 60)
		self.assertIsInstance(result, OEEResult)
		self.assertIs(result.ledger, ledger)
		self.assertEqual((result.good_count, result.scrap_count), (50, 5))

	def test_no_planned_time_gives_zero_availability(self):
		result = compute_oee(TimeLedger(planned_minutes=0, run_minutes=10), 10, 0, 60)
		self.assertEqual(result.availability, 0.0)
		self.assertEqual(result.oee, 0.0)

	def test_planned_downtime_covering_the_plan_gives_zero_availability(self):
		ledger = TimeLedger(planned_minutes=60, run_minutes=0, planned_downtime_minutes=60)
		self.assertEqual(compute_oee(ledger, 0, 0, 60).availability, 0.0)

	def test_availability_is_capped_at_one(self):
		# Intervals that overrun the plan cannot make availability exceed 100 percent.
		result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=90), 10, 0, None)
		self.assertEqual(result.availability, 1.0)

	def test_no_counts_gives_zero_quality_and_performance(self):
		result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=60), 0, 0, 60)
		self.assertEqual(result.quality, 0.0)
		self.assertEqual(result.performance, 0.0)
		self.assertEqual(result.oee, 0.0)

	def test_none_counts_are_treated_as_zero(self):
		result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=60), None, None, 60)
		self.assertEqual((result.quality, result.performance), (0.0, 0.0))

	def test_scrap_only_gives_zero_quality(self):
		result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=60), 0, 10, 60)
		self.assertEqual(result.quality, 0.0)
		self.assertGreater(result.performance, 0.0)

	def test_no_run_time_gives_zero_performance_even_with_counts(self):
		result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=0), 10, 0, 60)
		self.assertEqual(result.performance, 0.0)
		self.assertEqual(result.quality, 1.0)

	def test_zero_or_negative_cycle_time_is_like_none(self):
		for cycle in (0, -5):
			result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=60), 10, 0, cycle)
			self.assertEqual(result.performance, 1.0)
			self.assertTrue(any("no ideal cycle time" in n for n in result.notes))

	def test_performance_exactly_at_rated_speed_is_not_flagged(self):
		result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=60), 60, 0, 60)
		self.assertAlmostEqual(result.performance, 1.0)
		self.assertFalse(any("above 100" in n for n in result.notes))

	def test_notes_for_unknown_time_show_whole_minutes(self):
		ledger = TimeLedger(planned_minutes=60, run_minutes=30, unknown_minutes=30.4)
		result = compute_oee(ledger, 10, 0, 60)
		self.assertIn("30 minutes without a machine signal counted as loss", result.notes)

	def test_no_notes_on_a_clean_period(self):
		result = compute_oee(TimeLedger(planned_minutes=60, run_minutes=60), 30, 0, 60)
		self.assertEqual(result.notes, [])

	def test_oee_is_the_product_of_its_factors_and_never_exceeds_them(self):
		rng = random.Random(7)
		for _ in range(200):
			planned = rng.uniform(1, 1440)
			ledger = ledger_from_states(
				[
					(
						rng.uniform(0, planned / 2),
						rng.choice(["Running", "Idle", "Down", "Setup", "Unknown"]),
						rng.random() < 0.5,
					)
					for _ in range(rng.randint(0, 6))
				],
				planned,
			)
			good, scrap = rng.uniform(0, 500), rng.uniform(0, 50)
			cycle = rng.choice([None, 0, rng.uniform(1, 600)])
			result = compute_oee(ledger, good, scrap, cycle)
			for value in (result.availability, result.performance, result.quality, result.oee):
				self.assertGreaterEqual(value, 0.0)
				self.assertLessEqual(value, 1.0)
			self.assertAlmostEqual(result.oee, result.availability * result.performance * result.quality)
			self.assertLessEqual(
				result.oee, min(result.availability, result.performance, result.quality) + 1e-12
			)


if __name__ == "__main__":
	unittest.main()
