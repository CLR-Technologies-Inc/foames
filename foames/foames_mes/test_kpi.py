# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The report arithmetic, without a site."""

import unittest
from datetime import datetime

from foames.foames_mes.kpi import (
	clip_minutes,
	pareto,
	percentile,
	reliability,
	resolution_hours,
	roll_up_oee,
)


def period(planned, run, good, scrap, ideal=60.0, planned_dt=0.0, **extra):
	return {
		"planned_minutes": planned,
		"run_minutes": run,
		"planned_downtime_minutes": planned_dt,
		"unplanned_downtime_minutes": planned - run - planned_dt,
		"unknown_minutes": 0,
		"good_count": good,
		"scrap_count": scrap,
		"ideal_cycle_seconds": ideal,
		**extra,
	}


class TestRollUpOEE(unittest.TestCase):
	def test_single_period_matches_its_own_components(self):
		result = roll_up_oee([period(480, 400, 380, 20)])
		self.assertAlmostEqual(result["availability"], 400 / 480 * 100)
		self.assertAlmostEqual(result["performance"], 100)  # 400 units possible at 60 s, 400 counted
		self.assertAlmostEqual(result["quality"], 95)
		self.assertAlmostEqual(result["oee"], 400 / 480 * 0.95 * 100)

	def test_roll_up_is_time_weighted_not_an_average_of_percentages(self):
		long_shift = period(480, 480, 480, 0)  # 100 percent OEE all day
		short_trial = period(60, 30, 15, 15)  # 50 percent availability, poor quality
		result = roll_up_oee([long_shift, short_trial])
		self.assertAlmostEqual(result["availability"], 510 / 540 * 100)
		self.assertAlmostEqual(result["quality"], 495 / 510 * 100)
		# An average of the two OEE percentages would be about 56; the weighted figure is far higher.
		self.assertGreater(result["oee"], 85)

	def test_planned_downtime_leaves_the_availability_base(self):
		result = roll_up_oee([period(480, 420, 420, 0, planned_dt=60)])
		self.assertAlmostEqual(result["availability"], 100)

	def test_period_without_ideal_cycle_keeps_its_stored_performance(self):
		known = period(240, 240, 240, 0, ideal=60)
		unknown = period(240, 240, 100, 0, ideal=0, performance=50)
		result = roll_up_oee([known, unknown])
		self.assertAlmostEqual(result["performance"], (240 + 120) / 480 * 100)

	def test_performance_is_capped(self):
		result = roll_up_oee([period(60, 60, 200, 0)])
		self.assertAlmostEqual(result["performance"], 100)

	def test_empty_input(self):
		result = roll_up_oee([])
		self.assertEqual((result["periods"], result["oee"], result["availability"]), (0, 0, 0))


class TestPareto(unittest.TestCase):
	def test_orders_and_accumulates(self):
		rows = [
			{"label": "Jam", "minutes": 30},
			{"label": "Changeover", "minutes": 50},
			{"label": "Jam", "minutes": 20},
			{"label": None, "minutes": 10},
		]
		result = pareto(rows)
		self.assertEqual([r["label"] for r in result], ["Jam", "Changeover", "Unclassified"])
		self.assertEqual([r["occurrences"] for r in result], [2, 1, 1])
		self.assertAlmostEqual(result[0]["share"], 50 / 110 * 100)
		self.assertAlmostEqual(result[-1]["cumulative_share"], 100)

	def test_empty(self):
		self.assertEqual(pareto([]), [])


class TestClipMinutes(unittest.TestCase):
	def test_clips_to_the_window(self):
		w0, w1 = datetime(2026, 10, 1), datetime(2026, 10, 2)
		self.assertAlmostEqual(
			clip_minutes(datetime(2026, 9, 30, 23, 0), datetime(2026, 10, 1, 1, 0), w0, w1), 60
		)
		self.assertAlmostEqual(clip_minutes(datetime(2026, 10, 1, 23, 30), None, w0, w1), 30)
		self.assertEqual(clip_minutes(datetime(2026, 10, 3), datetime(2026, 10, 4), w0, w1), 0)


class TestReliability(unittest.TestCase):
	def test_mtbf_and_mttr(self):
		stats = reliability(failures=4, downtime_minutes=120, window_minutes=24 * 60)
		self.assertAlmostEqual(stats["mtbf_minutes"], (1440 - 120) / 4)
		self.assertAlmostEqual(stats["mttr_minutes"], 30)
		self.assertAlmostEqual(stats["availability"], 330 / 360 * 100)

	def test_no_failures(self):
		stats = reliability(0, 0, 1440)
		self.assertIsNone(stats["mtbf_minutes"])
		self.assertEqual((stats["mttr_minutes"], stats["availability"]), (0.0, 100.0))


class TestSmallHelpers(unittest.TestCase):
	def test_resolution_hours(self):
		a = datetime(2026, 10, 1, 8)
		pairs = [(a, datetime(2026, 10, 1, 10)), (a, datetime(2026, 10, 1, 14)), (a, None)]
		stats = resolution_hours(pairs)
		self.assertEqual(stats["resolved"], 2)
		self.assertAlmostEqual(stats["median_hours"], 4)
		self.assertAlmostEqual(stats["mean_hours"], 4)
		self.assertIsNone(resolution_hours([])["median_hours"])

	def test_percentile(self):
		self.assertEqual(percentile([5, 1, 3, 2, 4], 0.5), 3)
		self.assertEqual(percentile([5, 1, 3, 2, 4], 0.9), 5)
		self.assertIsNone(percentile([], 0.9))
