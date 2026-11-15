import unittest
from datetime import datetime, timedelta, timezone

from foames.foames_mes.oee import compute_oee, ledger_from_timeline

T = datetime(2026, 11, 4, 6, 0)


def at(minutes, base=T):
	return base + timedelta(minutes=minutes)


class TestTimeline(unittest.TestCase):
	def test_full_coverage(self):
		changes = [
			(at(0), "Running", False),
			(at(60), "Down", False),
			(at(80), "Running", False),
			(at(200), "Setup", False),
			(at(230), "Down", True),
			(at(260), "Idle", False),
		]
		ledger = ledger_from_timeline(changes, T, at(480))
		self.assertAlmostEqual(ledger.planned_minutes, 480)
		self.assertAlmostEqual(ledger.run_minutes, 180)
		self.assertAlmostEqual(ledger.unplanned_downtime_minutes, 20)
		self.assertAlmostEqual(ledger.setup_minutes, 30)
		self.assertAlmostEqual(ledger.planned_downtime_minutes, 30)
		self.assertAlmostEqual(ledger.idle_minutes, 220)
		self.assertAlmostEqual(ledger.unknown_minutes, 0)

	def test_unordered_input(self):
		changes = [(at(60), "Down", False), (at(0), "Running", False)]
		ledger = ledger_from_timeline(changes, T, at(120))
		self.assertAlmostEqual(ledger.run_minutes, 60)
		self.assertAlmostEqual(ledger.unplanned_downtime_minutes, 60)

	def test_state_from_before_the_window(self):
		changes = [(at(-90), "Running", False), (at(30), "Idle", False)]
		ledger = ledger_from_timeline(changes, T, at(60))
		self.assertAlmostEqual(ledger.run_minutes, 30)
		self.assertAlmostEqual(ledger.idle_minutes, 30)
		self.assertAlmostEqual(ledger.unknown_minutes, 0)

	def test_events_after_the_window_are_ignored(self):
		changes = [(at(0), "Running", False), (at(500), "Down", False)]
		ledger = ledger_from_timeline(changes, T, at(480))
		self.assertAlmostEqual(ledger.run_minutes, 480)

	def test_gap_before_first_event(self):
		ledger = ledger_from_timeline([(at(45), "Running", False)], T, at(120))
		self.assertAlmostEqual(ledger.unknown_minutes, 45)
		self.assertAlmostEqual(ledger.run_minutes, 75)

	def test_staleness_cuts_a_long_state(self):
		changes = [(at(0), "Running", False), (at(200), "Running", False)]
		ledger = ledger_from_timeline(changes, T, at(240), stale_after_minutes=60)
		self.assertAlmostEqual(ledger.run_minutes, 60 + 40)
		self.assertAlmostEqual(ledger.unknown_minutes, 140)

	def test_staleness_applies_to_the_last_state(self):
		ledger = ledger_from_timeline([(at(0), "Down", True)], T, at(100), stale_after_minutes=30)
		self.assertAlmostEqual(ledger.planned_downtime_minutes, 30)
		self.assertAlmostEqual(ledger.unknown_minutes, 70)

	def test_aware_datetimes(self):
		base = datetime(2026, 11, 4, 6, 0, tzinfo=timezone.utc)
		ledger = ledger_from_timeline([(at(0, base), "Running", False)], base, at(60, base))
		self.assertAlmostEqual(ledger.run_minutes, 60)

	def test_empty_timeline_is_all_unknown(self):
		ledger = ledger_from_timeline([], T, at(60))
		self.assertAlmostEqual(ledger.unknown_minutes, 60)
		self.assertAlmostEqual(ledger.run_minutes, 0)

	def test_bad_window(self):
		with self.assertRaises(ValueError):
			ledger_from_timeline([], at(60), T)
		with self.assertRaises(ValueError):
			ledger_from_timeline([], T, T)

	def test_oee_from_timeline(self):
		changes = [(at(0), "Running", False), (at(240), "Down", True)]
		ledger = ledger_from_timeline(changes, T, at(480), stale_after_minutes=None)
		result = compute_oee(ledger, good_count=900, scrap_count=100, ideal_cycle_seconds=12)
		# availability base excludes planned downtime: 240 / (480 - 240)
		self.assertAlmostEqual(result.availability, 1.0)
		self.assertAlmostEqual(result.performance, (12 * 1000 / 60) / 240)
		self.assertAlmostEqual(result.quality, 0.9)
