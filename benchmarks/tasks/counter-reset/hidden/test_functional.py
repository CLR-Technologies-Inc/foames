import itertools
import unittest

from foames.foames_mes.counters import counter_delta, good_and_scrap


class TestCounting(unittest.TestCase):
	def test_normal_increments(self):
		self.assertEqual(counter_delta(100, 112), 12.0)
		self.assertEqual(counter_delta(0, 5), 5.0)

	def test_unchanged_counter(self):
		self.assertEqual(counter_delta(48112, 48112), 0.0)

	def test_known_rollover_wraps(self):
		self.assertEqual(counter_delta(65530, 4, rollover=65535), 9.0)
		self.assertEqual(counter_delta(9990, 10, rollover=9999), 19.0)

	def test_night_shift_sequence(self):
		# The first reading after the restart already shows 37 parts; they cannot be told apart from
		# a bad reading, so they are not counted. Counting resumes from 37.
		readings = [48000, 48112, 37, 40, 95]
		total = sum(counter_delta(a, b) for a, b in itertools.pairwise(readings))
		self.assertEqual(total, 112 + 3 + 55)

	def test_good_and_scrap(self):
		self.assertEqual(good_and_scrap({"good": 10, "scrap": 2, "energy_kwh": 5}), (10.0, 2.0))
