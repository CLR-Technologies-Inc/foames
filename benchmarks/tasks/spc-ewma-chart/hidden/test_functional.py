import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import itertools

from _reference_math import expected

from foames.foames_mes.spc import ewma_chart


def series(seed, n=80, shift_at=None, shift=0.0, mean=50.0, sd=1.0):
	rng = random.Random(seed)
	return [
		mean + rng.gauss(0, sd) + (shift if shift_at is not None and i >= shift_at else 0.0) for i in range(n)
	]


class TestEWMAValues(unittest.TestCase):
	def assertChartMatches(self, values, lam, L, baseline):
		got = ewma_chart(values, lam=lam, L=L, baseline=baseline)
		want = expected(values, lam, L, baseline)
		self.assertEqual(got["chart"], "EWMA")
		self.assertAlmostEqual(got["cl"], want["cl"], places=9)
		self.assertAlmostEqual(got["sigma_within"], want["sigma"], places=4)
		self.assertEqual(len(got["points"]), len(values))
		for key in ("points", "ucl", "lcl"):
			for a, b in zip(got[key], want[key], strict=False):
				self.assertAlmostEqual(a, b, places=4)
		self.assertEqual([s["index"] for s in got["signals"]], want["signals"])
		self.assertTrue(all(s["rule"] == "EWMA" for s in got["signals"]))
		self.assertEqual((got["lambda"], got["L"]), (lam, L))

	def test_defaults(self):
		self.assertChartMatches(series(1), 0.2, 3.0, None)

	def test_with_baseline_and_shift(self):
		self.assertChartMatches(series(2, shift_at=40, shift=1.0), 0.2, 3.0, 40)

	def test_other_parameters(self):
		self.assertChartMatches(series(3, shift_at=30, shift=-0.75), 0.1, 2.7, 30)
		self.assertChartMatches(series(4), 0.05, 2.5, 25)

	def test_baseline_points(self):
		self.assertEqual(ewma_chart(series(5), baseline=30)["baseline_points"], 30)
		self.assertEqual(ewma_chart(series(5, n=12))["baseline_points"], 12)

	def test_limits_widen_towards_the_asymptote(self):
		chart = ewma_chart(series(6), baseline=30)
		widths = [u - chart["cl"] for u in chart["ucl"]]
		self.assertTrue(all(b >= a for a, b in itertools.pairwise(widths)))

	def test_detects_a_one_sigma_shift(self):
		values = series(7, n=100, shift_at=50, shift=1.0)
		chart = ewma_chart(values, baseline=50)
		after = [s["index"] for s in chart["signals"] if s["index"] >= 50]
		self.assertTrue(after, "a 1-sigma shift should signal within 50 points")

	def test_bad_arguments(self):
		for kwargs in ({"lam": 0}, {"lam": 1.5}, {"lam": -0.1}, {"L": 0}, {"L": -1}):
			with self.assertRaises(ValueError):
				ewma_chart(series(8), **kwargs)
		with self.assertRaises(ValueError):
			ewma_chart([1.0])
		with self.assertRaises(ValueError):
			ewma_chart(series(8), baseline=1)
