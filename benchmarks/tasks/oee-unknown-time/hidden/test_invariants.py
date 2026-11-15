import random
import unittest
from datetime import datetime, timedelta

from foames.foames_mes.oee import compute_oee, ledger_from_timeline

T = datetime(2026, 11, 4, 6, 0)
STATES = ["Running", "Idle", "Down", "Setup", "Unknown"]


def at(minutes):
	return T + timedelta(minutes=minutes)


def random_timeline(rng, n=30, span=480):
	return [(at(rng.uniform(-60, span + 60)), rng.choice(STATES), rng.random() < 0.3) for _ in range(n)]


class TestUnknownTimeIsLoss(unittest.TestCase):
	def test_every_minute_is_accounted_once(self):
		rng = random.Random(3)
		for _ in range(200):
			stale = rng.choice([None, 15, 60])
			ledger = ledger_from_timeline(random_timeline(rng), T, at(480), stale_after_minutes=stale)
			self.assertAlmostEqual(ledger.accounted_minutes, 480, places=6)

	def test_a_gap_is_unknown_not_run(self):
		changes = [(at(0), "Running", False), (at(100), "Running", False)]
		ledger = ledger_from_timeline(changes, T, at(200), stale_after_minutes=10)
		self.assertAlmostEqual(ledger.run_minutes, 20)
		self.assertAlmostEqual(ledger.unknown_minutes, 180)

	def test_unknown_state_is_never_run(self):
		ledger = ledger_from_timeline([(at(0), "Unknown", False)], T, at(60))
		self.assertEqual(ledger.run_minutes, 0)
		self.assertAlmostEqual(ledger.unknown_minutes, 60)

	def test_unrecognised_state_is_unknown(self):
		ledger = ledger_from_timeline([(at(0), "Offline", False)], T, at(60))
		self.assertEqual(ledger.run_minutes, 0)
		self.assertAlmostEqual(ledger.unknown_minutes, 60)

	def test_staleness_never_adds_run_time(self):
		rng = random.Random(5)
		for _ in range(200):
			timeline = random_timeline(rng)
			loose = ledger_from_timeline(timeline, T, at(480))
			tight = ledger_from_timeline(timeline, T, at(480), stale_after_minutes=20)
			self.assertLessEqual(tight.run_minutes, loose.run_minutes + 1e-9)
			self.assertGreaterEqual(tight.unknown_minutes, loose.unknown_minutes - 1e-9)

	def test_unknown_time_lowers_availability(self):
		full = ledger_from_timeline([(at(0), "Running", False)], T, at(480))
		gappy = ledger_from_timeline([(at(0), "Running", False)], T, at(480), stale_after_minutes=240)
		a = compute_oee(full, 100, 0, None).availability
		b = compute_oee(gappy, 100, 0, None).availability
		self.assertAlmostEqual(a, 1.0)
		self.assertAlmostEqual(b, 0.5)

	def test_input_is_not_mutated(self):
		changes = [(at(60), "Down", False), (at(0), "Running", False)]
		copy = list(changes)
		ledger_from_timeline(changes, T, at(120))
		self.assertEqual(changes, copy)

	def test_module_stays_pure(self):
		import foames.foames_mes.oee as oee

		source = open(oee.__file__, encoding="utf-8").read()
		self.assertNotIn("import frappe", source)
		self.assertNotIn("from frappe", source)
