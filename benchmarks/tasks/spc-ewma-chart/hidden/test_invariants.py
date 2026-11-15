import random
import unittest

from foames.foames_mes import spc
from foames.foames_mes.spc import ewma_chart


def series(seed, n=80, mean=50.0, sd=1.0):
	rng = random.Random(seed)
	return [mean + rng.gauss(0, sd) for _ in range(n)]


class TestJudgedAgainstThePast(unittest.TestCase):
	def test_new_values_do_not_move_the_limits(self):
		base = series(10, n=40)
		a = ewma_chart(base + [50.0] * 10, baseline=40)
		b = ewma_chart(base + [58.0] * 10, baseline=40)
		self.assertAlmostEqual(a["cl"], b["cl"])
		self.assertAlmostEqual(a["sigma_within"], b["sigma_within"])
		self.assertEqual(a["ucl"], b["ucl"])

	def test_lambda_one_is_an_individuals_chart(self):
		values = series(11)
		e = ewma_chart(values, lam=1.0, L=3.0)
		i = spc.imr_chart(values)["individuals"]
		self.assertAlmostEqual(e["cl"], i["cl"], places=9)
		for z, x in zip(e["points"], values, strict=False):
			self.assertAlmostEqual(z, x, places=9)
		for u in e["ucl"]:
			self.assertAlmostEqual(u, i["ucl"], places=6)
		self.assertEqual(
			[s["index"] for s in e["signals"]],
			sorted({s["index"] for s in i["signals"] if s["rule"] == "N1"}),
		)

	def test_false_alarm_rate_is_bounded(self):
		# In control, lambda 0.2 and L 3 give an average run length near 500, so about half of 40
		# series of 300 points alarm somewhere (the exact limits give 22 here). Limits that are too
		# narrow, such as sigma * lambda, alarm on nearly every series.
		alarms = sum(bool(ewma_chart(series(100 + k, n=300), baseline=200)["signals"]) for k in range(40))
		self.assertLessEqual(alarms, 28)

	def test_existing_charts_unchanged(self):
		values = series(12)
		chart = spc.imr_chart(values, baseline=30)
		self.assertIn("individuals", chart)
		self.assertIn("moving_range", chart)

	def test_module_stays_pure(self):
		source = open(spc.__file__, encoding="utf-8").read()
		self.assertNotIn("import frappe", source)
		self.assertNotIn("from frappe", source)
