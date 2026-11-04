import random
import unittest

from foames.foames_mes.counters import counter_delta


class TestCountersNeverInventProduction(unittest.TestCase):
	def test_first_reading_is_zero(self):
		self.assertEqual(counter_delta(None, 48112), 0.0)

	def test_reset_is_zero(self):
		self.assertEqual(counter_delta(48112, 0), 0.0)
		self.assertEqual(counter_delta(48112, 4800), 0.0)

	def test_out_of_order_is_zero(self):
		self.assertEqual(counter_delta(500, 499), 0.0)

	def test_unknown_rollover_is_a_reset(self):
		self.assertEqual(counter_delta(65530, 4), 0.0)
		self.assertEqual(counter_delta(65530, 4, rollover=0), 0.0)

	def test_reading_above_a_known_rollover_is_not_a_wrap(self):
		# previous above the rollover value cannot wrap; it is bad data or a reset.
		self.assertEqual(counter_delta(70000, 4, rollover=65535), 0.0)

	def test_never_negative_and_never_more_than_the_rise(self):
		rng = random.Random(7)
		for _ in range(2000):
			a, b = rng.randint(0, 10_000), rng.randint(0, 10_000)
			d = counter_delta(a, b)
			self.assertGreaterEqual(d, 0.0)
			self.assertLessEqual(d, max(b - a, 0))

	def test_sum_never_exceeds_the_true_count(self):
		# A counter that makes 1 part per reading, with resets: counted <= made.
		rng = random.Random(11)
		made, value, previous, counted = 0, 0, None, 0.0
		for _ in range(500):
			if rng.random() < 0.05:
				value = 0
			else:
				value += 1
				made += 1
			counted += counter_delta(previous, value)
			previous = value
		self.assertLessEqual(counted, made)
