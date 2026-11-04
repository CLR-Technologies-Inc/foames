"""Reference solution for oee-unknown-time."""

from pathlib import Path

CODE = '''

def ledger_from_timeline(changes, period_start, period_end, stale_after_minutes=None) -> TimeLedger:
	"""Build a ledger from (timestamp, state, planned) state changes over [period_start, period_end).

	A state holds until the next change, or for at most `stale_after_minutes` after the event that
	reported it. Time before the first known state, and time past the staleness limit, is Unknown:
	the absence of events is never read as run time."""
	from datetime import timedelta

	if period_end <= period_start:
		raise ValueError("period_end must be after period_start")
	planned_minutes = (period_end - period_start).total_seconds() / 60.0
	ordered = sorted(changes, key=lambda c: c[0])
	intervals = []
	for i, (at, state, planned) in enumerate(ordered):
		until = ordered[i + 1][0] if i + 1 < len(ordered) else period_end
		if stale_after_minutes is not None:
			until = min(until, at + timedelta(minutes=stale_after_minutes))
		start, end = max(at, period_start), min(until, period_end)
		if end > start:
			intervals.append(((end - start).total_seconds() / 60.0, state, bool(planned)))
	# ledger_from_states files anything it does not know, and every uncovered minute, as unknown.
	return ledger_from_states(intervals, planned_minutes)
'''

TEST = """import unittest
from datetime import datetime

from foames.foames_mes.oee import ledger_from_timeline

T = datetime(2026, 11, 4, 6, 0)


def at(minutes):
	from datetime import timedelta

	return T + timedelta(minutes=minutes)


class TestLedgerFromTimeline(unittest.TestCase):
	def test_gap_before_first_event_is_unknown(self):
		ledger = ledger_from_timeline([(at(30), "Running", False)], T, at(120))
		self.assertAlmostEqual(ledger.unknown_minutes, 30)
		self.assertAlmostEqual(ledger.run_minutes, 90)

	def test_stale_state_becomes_unknown(self):
		ledger = ledger_from_timeline([(at(0), "Running", False)], T, at(120), stale_after_minutes=60)
		self.assertAlmostEqual(ledger.run_minutes, 60)
		self.assertAlmostEqual(ledger.unknown_minutes, 60)
"""


def apply(workspace: Path):
	path = workspace / "foames" / "foames_mes" / "oee.py"
	path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + CODE, encoding="utf-8")
	(workspace / "foames" / "foames_mes" / "test_oee_timeline.py").write_text(TEST, encoding="utf-8")
	(workspace / "BENCH_NOTES.md").write_text(
		"Reference solution. ledger_from_timeline sorts the changes, clips each state to the window and to "
		"the staleness limit, and hands the intervals to ledger_from_states, which files uncovered time and "
		"unrecognised states as Unknown. Unknown time stays in the availability base, so a gateway outage "
		"lowers availability instead of being read as run time (AGENTS.md invariant 4). What the machine did "
		"during a gap cannot be known from this data.\n",
		encoding="utf-8",
	)
