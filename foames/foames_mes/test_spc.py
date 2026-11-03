# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Control chart limits, the Nelson and Western Electric run rules, and SPC findings. No Frappe site
needed. The reference data and limits are ops-library's (02-quality-and-statistics/tools/data)."""

import csv
import os
import unittest
from datetime import datetime, timedelta

from foames.foames_mes import spc

DATA = os.path.join(os.path.dirname(__file__), "test_data")
# ops-library reference_results.json, computed by opex_stats from the same files
IMR_REFERENCE = {
	"cl": 10.005101999999999,
	"lcl": 9.917123836127779,
	"ucl": 10.09308016387222,
	"mr_bar": 0.03309090909090929,
	"mr_ucl": 0.10809229379197685,
}
XBAR_R_REFERENCE = {
	"xbar_cl": 10.001792,
	"xbar_lcl": 9.963486581662078,
	"xbar_ucl": 10.040097418337922,
	"r_bar": 0.06640800000000013,
	"r_ucl": 0.14042120603591074,
}


def read(name):
	with open(os.path.join(DATA, name)) as f:
		return list(csv.DictReader(f))


def rules_at(signals, index):
	return {s["rule"] for s in signals if s["index"] == index}


def fired(signals):
	return {s["rule"] for s in signals}


class TestFactors(unittest.TestCase):
	def test_published_table_values(self):
		# AIAG SPC manual tables, to their rounding
		for n, a2, d4 in ((2, 1.880, 3.267), (5, 0.577, 2.114), (10, 0.308, 1.777)):
			f = spc.factors(n)
			self.assertAlmostEqual(f["A2"], a2, delta=0.001)
			self.assertAlmostEqual(f["D4"], d4, delta=0.001)
		self.assertAlmostEqual(spc.factors(7)["D3"], 0.076, delta=0.001)
		self.assertEqual(spc.factors(6)["D3"], 0.0)

	def test_subgroup_size_out_of_range(self):
		for n in (1, 26):
			with self.assertRaises(ValueError):
				spc.factors(n)


class TestCharts(unittest.TestCase):
	def test_imr_matches_ops_library(self):
		values = [float(r["diameter_mm"]) for r in read("spc_individuals.csv")]
		chart = spc.imr_chart(values)
		self.assertAlmostEqual(chart["individuals"]["cl"], IMR_REFERENCE["cl"], places=9)
		self.assertAlmostEqual(chart["individuals"]["ucl"], IMR_REFERENCE["ucl"], places=9)
		self.assertAlmostEqual(chart["individuals"]["lcl"], IMR_REFERENCE["lcl"], places=9)
		self.assertAlmostEqual(chart["moving_range"]["cl"], IMR_REFERENCE["mr_bar"], places=9)
		self.assertAlmostEqual(chart["moving_range"]["ucl"], IMR_REFERENCE["mr_ucl"], places=9)
		self.assertEqual(chart["moving_range"]["lcl"], 0.0)

	def test_xbar_r_matches_ops_library(self):
		groups = {}
		for r in read("spc_subgroups.csv"):
			groups.setdefault(int(r["subgroup"]), []).append(float(r["diameter_mm"]))
		chart = spc.xbar_r_chart([groups[k] for k in sorted(groups)])
		self.assertAlmostEqual(chart["xbar"]["cl"], XBAR_R_REFERENCE["xbar_cl"], places=9)
		self.assertAlmostEqual(chart["xbar"]["ucl"], XBAR_R_REFERENCE["xbar_ucl"], places=9)
		self.assertAlmostEqual(chart["xbar"]["lcl"], XBAR_R_REFERENCE["xbar_lcl"], places=9)
		self.assertAlmostEqual(chart["range"]["cl"], XBAR_R_REFERENCE["r_bar"], places=9)
		self.assertAlmostEqual(chart["range"]["ucl"], XBAR_R_REFERENCE["r_ucl"], places=9)

	def test_baseline_sets_the_limits_and_later_points_are_judged(self):
		values = [10, 11] * 10 + [30]
		full = spc.imr_chart(values)
		base = spc.imr_chart(values, baseline=20)
		self.assertAlmostEqual(base["individuals"]["cl"], 10.5)
		self.assertAlmostEqual(base["moving_range"]["cl"], 1.0)
		self.assertEqual(base["baseline_points"], 20)
		self.assertIn("N1", rules_at(base["individuals"]["signals"], 20))
		self.assertGreater(full["individuals"]["ucl"], base["individuals"]["ucl"])

	def test_moving_range_chart_only_uses_the_limit_rule(self):
		chart = spc.imr_chart([10, 11] * 10 + [30, 30, 30])
		self.assertTrue(chart["moving_range"]["signals"])
		self.assertEqual(fired(chart["moving_range"]["signals"]), {"N1"})

	def test_subgroups_drop_the_short_tail(self):
		self.assertEqual(spc.subgroups_of(range(7), 3), [[0, 1, 2], [3, 4, 5]])

	def test_unequal_subgroups_are_refused(self):
		with self.assertRaises(ValueError):
			spc.xbar_r_chart([[1, 2], [1, 2, 3]])

	def test_imr_needs_two_values(self):
		with self.assertRaises(ValueError):
			spc.imr_chart([1.0])


class TestRunRules(unittest.TestCase):
	"""cl 0, limits +-3, so each unit is one sigma."""

	def rules(self, points, rules="Nelson"):
		return spc.run_rules(points, 0.0, 3.0, -3.0, rules)

	def test_n1_beyond_the_limits_but_not_on_them(self):
		signals = self.rules([0, 3.0, -3.0, 3.01, -4])
		self.assertEqual([s["index"] for s in signals if s["rule"] == "N1"], [3, 4])

	def test_n2_nine_on_one_side(self):
		self.assertEqual(rules_at(self.rules([0.5] * 9), 8) & {"N2"}, {"N2"})
		self.assertNotIn("N2", fired(self.rules([0.5] * 8)))
		self.assertNotIn("N2", fired(self.rules([0.5] * 4 + [0] + [0.5] * 4)))

	def test_n3_six_increasing(self):
		self.assertIn("N3", rules_at(self.rules([-1, -0.6, -0.2, 0.2, 0.6, 1.0]), 5))
		self.assertNotIn("N3", fired(self.rules([-1, -0.6, -0.2, 0.2, 0.6])))
		self.assertNotIn("N3", fired(self.rules([-1, -0.6, -0.6, 0.2, 0.6, 1.0])))

	def test_n4_fourteen_alternating(self):
		points = [0.5 if i % 2 else -0.5 for i in range(14)]
		self.assertIn("N4", rules_at(self.rules(points), 13))
		self.assertNotIn("N4", fired(self.rules(points[:13])))

	def test_n5_two_of_three_beyond_two_sigma(self):
		self.assertIn("N5", rules_at(self.rules([2.5, 0, 2.5]), 2))
		# on opposite sides it does not count
		self.assertNotIn("N5", fired(self.rules([2.5, 0, -2.5])))
		# the signal lands on the point that completes the pattern, not a calm one after it
		self.assertEqual([s["index"] for s in self.rules([2.5, 2.5, 0]) if s["rule"] == "N5"], [1])

	def test_n6_four_of_five_beyond_one_sigma(self):
		self.assertIn("N6", rules_at(self.rules([1.5, 1.5, 0, 1.5, 1.5]), 4))
		self.assertNotIn("N6", fired(self.rules([1.5, 1.5, 0, 0, 1.5])))

	def test_n7_fifteen_hugging_the_centre(self):
		points = [0.2 if i % 3 else -0.2 for i in range(15)]
		self.assertIn("N7", rules_at(self.rules(points), 14))
		self.assertNotIn("N7", fired(self.rules(points[:14])))

	def test_n8_eight_avoiding_the_centre(self):
		points = [1.5, -1.5] * 4
		self.assertIn("N8", rules_at(self.rules(points), 7))
		self.assertNotIn("N8", fired(self.rules(points[:7])))

	def test_western_electric_set(self):
		signals = self.rules([0.5] * 8 + [4], "Western Electric")
		self.assertIn("WE4", rules_at(signals, 7))
		self.assertIn("WE1", rules_at(signals, 8))
		self.assertTrue(fired(signals) <= set(spc.RULE_SETS["Western Electric"]))

	def test_unknown_rules_are_refused(self):
		with self.assertRaises(ValueError):
			self.rules([0], "Shewhart")
		with self.assertRaises(ValueError):
			self.rules([0], ["N9"])

	def test_flat_series_has_no_zone_signals(self):
		self.assertEqual(spc.run_rules([5.0] * 20, 5.0, 5.0, 5.0, ["N5", "N6", "N7", "N8"]), [])

	def test_in_control_noise_is_quiet(self):
		values = [float(r["diameter_mm"]) for r in read("spc_individuals.csv")]
		chart = spc.imr_chart(values)
		self.assertNotIn("N1", fired(chart["individuals"]["signals"]))


class TestFindings(unittest.TestCase):
	start = datetime(2026, 11, 3, 8, 0)

	def series(self, values, measurement="temperature"):
		return {
			"machine": "M1",
			"measurement": measurement,
			"readings": [(self.start + timedelta(minutes=i), v) for i, v in enumerate(values)],
		}

	def recent_from(self, index):
		return self.start + timedelta(minutes=index)

	def test_a_spike_after_the_baseline_raises_one_finding_per_chart(self):
		values = [10, 11] * 15 + [30]
		found = spc.findings(self.series(values), recent_from=self.recent_from(30))
		keys = {f["rule_key"] for f in found}
		self.assertIn("spc:M1:temperature:I:N1", keys)
		self.assertIn("spc:M1:temperature:MR:N1", keys)
		spike = next(f for f in found if f["rule_key"] == "spc:M1:temperature:I:N1")
		self.assertEqual(spike["severity"], "Critical")
		self.assertEqual(spike["category"], "Quality")
		self.assertEqual(spike["reference_doctype"], "Machine")
		self.assertEqual(spike["reference_name"], "M1")
		ev = spike["evidence"]
		self.assertEqual(ev["latest_value"], 30.0)
		self.assertEqual(ev["latest_signal_at"], str(self.recent_from(30)))
		self.assertEqual(ev["baseline_points"], 30)
		self.assertAlmostEqual(ev["centre_line"], 10.5)
		self.assertIn("30", spike["suggestion"])

	def test_signals_in_the_baseline_are_not_reported(self):
		values = [10, 11] * 5 + [30] + [10, 11] * 10 + [10.5]
		found = spc.findings(self.series(values), recent_from=self.recent_from(31))
		self.assertEqual([f for f in found if f["evidence"]["rule"] == "N1"], [])

	def test_a_short_baseline_raises_nothing(self):
		values = [10, 11] * 5 + [30]
		self.assertEqual(spc.findings(self.series(values), recent_from=self.recent_from(10)), [])
		self.assertTrue(spc.findings(self.series(values), recent_from=self.recent_from(10), min_baseline=10))

	def test_nothing_recent_raises_nothing(self):
		values = [10, 11] * 15
		self.assertEqual(spc.findings(self.series(values), recent_from=self.recent_from(100)), [])

	def test_a_shift_raises_one_finding_however_many_points_signal(self):
		values = [10, 11] * 15 + [11.6] * 12
		found = [
			f
			for f in spc.findings(self.series(values), recent_from=self.recent_from(30))
			if f["evidence"]["rule"] == "N2"
		]
		self.assertEqual(len(found), 1)
		self.assertEqual(found[0]["severity"], "Warning")
		# the run starts on the last baseline reading (11), so the 9th point in a row is reading 37
		self.assertEqual(found[0]["evidence"]["signal_count"], 5)
		self.assertEqual(found[0]["evidence"]["latest_signal_at"], str(self.recent_from(41)))

	def test_xbar_r_findings_with_a_subgroup_size(self):
		values = [10, 11, 10.5, 10.2, 10.8] * 8 + [13, 13.5, 13.2, 13.1, 13.4]
		found = spc.findings(self.series(values), recent_from=self.recent_from(40), subgroup_size=5)
		xbar = [f for f in found if f["evidence"]["chart"] == "X-bar"]
		self.assertTrue(xbar)
		self.assertEqual(xbar[0]["evidence"]["subgroup_size"], 5)
		self.assertEqual(xbar[0]["evidence"]["latest_signal_at"], str(self.recent_from(44)))

	def test_western_electric_keys(self):
		values = [10, 11] * 15 + [30]
		found = spc.findings(self.series(values), recent_from=self.recent_from(30), rules="Western Electric")
		self.assertIn("spc:M1:temperature:I:WE1", {f["rule_key"] for f in found})
		self.assertIn("spc:M1:temperature:MR:WE1", {f["rule_key"] for f in found})

	def test_missing_values_are_skipped(self):
		values = [10, 11] * 15 + [None, 30]
		found = spc.findings(self.series(values), recent_from=self.recent_from(30))
		self.assertIn("spc:M1:temperature:I:N1", {f["rule_key"] for f in found})


if __name__ == "__main__":
	unittest.main()
