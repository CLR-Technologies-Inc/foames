import json
import os
import unittest
from pathlib import Path

EXPECTED = json.loads((Path(__file__).parent / "expected.json").read_text(encoding="utf-8"))
WORKSPACE = Path(os.environ["FOAMES_BENCH_WORKSPACE"])


def answers():
	return json.loads((WORKSPACE / "answers.json").read_text(encoding="utf-8"))


class TestAnswers(unittest.TestCase):
	def test_cases(self):
		self.assertEqual(answers()["cases"], EXPECTED["cases"])

	def test_variants(self):
		self.assertEqual(answers()["variants"], EXPECTED["variants"])

	def test_top_variant(self):
		got = answers()["top_variant"]
		self.assertEqual(list(got["activities"]), EXPECTED["top_variant"]["activities"])
		self.assertEqual(got["cases"], EXPECTED["top_variant"]["cases"])

	def test_median_cycle_time(self):
		self.assertAlmostEqual(
			float(answers()["median_cycle_time_minutes"]), EXPECTED["median_cycle_time_minutes"], delta=0.5
		)

	def test_rework(self):
		got = {k: int(v) for k, v in answers()["rework_cases"].items() if int(v) > 0}
		self.assertEqual(got, EXPECTED["rework_cases"])

	def test_bottleneck(self):
		self.assertEqual(answers()["bottleneck"], EXPECTED["bottleneck"])

	def test_incomplete_cases(self):
		self.assertEqual(sorted(answers()["incomplete_cases"]), EXPECTED["incomplete_cases"])
