# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Finite-capacity scheduling, without a site."""

import unittest
from datetime import datetime, timedelta

from foames.foames_mes.scheduling import (
	Operation,
	behind_schedule_findings,
	current_and_next,
	merge,
	place,
	schedule,
	subtract,
)

START = datetime(2026, 11, 16, 6, 0)  # a Monday


def at(hours: float) -> datetime:
	return START + timedelta(hours=hours)


def day_shifts(days=5, hours=8):
	"""06:00 to 14:00 on `days` consecutive days."""
	return [(at(24 * d), at(24 * d + hours)) for d in range(days)]


def op(key, job, seq, machines, **kw):
	return Operation(key=key, job=job, sequence=seq, machines=machines, **kw)


class TestWindows(unittest.TestCase):
	def test_merge_joins_touching_and_overlapping(self):
		self.assertEqual(
			merge([(at(2), at(3)), (at(0), at(1)), (at(1), at(2)), (at(5), at(6))]),
			[(at(0), at(3)), (at(5), at(6))],
		)

	def test_subtract_cuts_blocks(self):
		self.assertEqual(
			subtract([(at(0), at(8))], [(at(2), at(3)), (at(7), at(9))]),
			[(at(0), at(2)), (at(3), at(7))],
		)

	def test_place_splits_over_a_break(self):
		s, e, pieces = place([(at(0), at(2)), (at(3), at(5))], at(1), 120)
		self.assertEqual((s, e), (at(1), at(4)))
		self.assertEqual(pieces, [(at(1), at(2)), (at(3), at(4))])

	def test_place_without_split_waits_for_a_long_enough_window(self):
		s, e, _pieces = place([(at(0), at(2)), (at(3), at(6))], at(1), 120, split=False)
		self.assertEqual((s, e), (at(3), at(5)))
		self.assertIsNone(place([(at(0), at(1))], at(0), 120, split=False))

	def test_place_runs_out_of_windows(self):
		self.assertIsNone(place([(at(0), at(1))], at(0), 90))


class TestSchedule(unittest.TestCase):
	def test_operations_of_a_job_run_in_sequence(self):
		ops = [
			op("J1-20", "J1", 20, {"M2": (0, 60)}),
			op("J1-10", "J1", 10, {"M1": (0, 120)}),
		]
		result = schedule(ops, {"M1": day_shifts(), "M2": day_shifts()}, START, at(120))
		by_key = {s.key: s for s in result.slots}
		self.assertEqual(by_key["J1-10"].end, at(2))
		self.assertEqual(by_key["J1-20"].start, at(2))
		self.assertEqual(by_key["J1-20"].end, at(3))

	def test_transfer_time_delays_the_next_operation(self):
		ops = [
			op("a", "J", 10, {"M1": (0, 60)}),
			op("b", "J", 20, {"M2": (0, 60)}, transfer_minutes=30),
		]
		result = schedule(ops, {"M1": day_shifts(), "M2": day_shifts()}, START, at(120))
		self.assertEqual({s.key: s.start for s in result.slots}["b"], at(1.5))

	def test_one_operation_at_a_time_per_machine(self):
		ops = [op(f"J{i}", f"J{i}", 10, {"M1": (0, 60)}) for i in range(3)]
		result = schedule(ops, {"M1": day_shifts()}, START, at(120), rule="FIFO")
		self.assertEqual(
			[(s.start, s.end) for s in result.slots], [(at(0), at(1)), (at(1), at(2)), (at(2), at(3))]
		)

	def test_edd_puts_the_earliest_due_job_first(self):
		ops = [
			op("late", "A", 10, {"M1": (0, 60)}, due=at(48), order=0),
			op("soon", "B", 10, {"M1": (0, 60)}, due=at(4), order=1),
		]
		result = schedule(ops, {"M1": day_shifts()}, START, at(120), rule="EDD")
		self.assertEqual(result.slots[0].key, "soon")
		self.assertEqual(result.kpis["late_jobs"], [])

	def test_spt_puts_the_shortest_first(self):
		ops = [op("long", "A", 10, {"M1": (0, 240)}), op("short", "B", 10, {"M1": (0, 30)})]
		self.assertEqual(
			schedule(ops, {"M1": day_shifts()}, START, at(120), rule="SPT").slots[0].key, "short"
		)

	def test_priority_rule(self):
		ops = [
			op("low", "A", 10, {"M1": (0, 30)}, priority=1),
			op("high", "B", 10, {"M1": (0, 30)}, priority=5),
		]
		self.assertEqual(
			schedule(ops, {"M1": day_shifts()}, START, at(120), rule="Priority").slots[0].key, "high"
		)

	def test_critical_ratio_prefers_the_job_with_least_slack_per_minute_of_work(self):
		ops = [
			# 10 hours to due, 1 hour of work: ratio 10
			op("easy", "A", 10, {"M1": (0, 60)}, due=at(10)),
			# 12 hours to due, 6 hours of work: ratio 2
			op("tight", "B", 10, {"M1": (0, 360)}, due=at(12)),
		]
		self.assertEqual(
			schedule(ops, {"M1": [(at(0), at(100))]}, START, at(120), rule="CR").slots[0].key, "tight"
		)

	def test_picks_the_machine_that_finishes_first(self):
		ops = [
			op("first", "A", 10, {"M1": (0, 120)}),
			op("second", "B", 10, {"M1": (0, 60), "M2": (0, 90)}),
		]
		result = schedule(ops, {"M1": day_shifts(), "M2": day_shifts()}, START, at(120), rule="FIFO")
		self.assertEqual({s.key: s.machine for s in result.slots}["second"], "M2")

	def test_work_pauses_overnight_when_split(self):
		ops = [op("big", "A", 10, {"M1": (30, 600)})]
		slot = schedule(ops, {"M1": day_shifts()}, START, at(120)).slots[0]
		self.assertTrue(slot.split)
		self.assertEqual(slot.end, at(24 + 2.5))

	def test_unsplit_work_longer_than_a_shift_is_unscheduled(self):
		ops = [op("big", "A", 10, {"M1": (0, 600)}), op("next", "A", 20, {"M1": (0, 10)})]
		result = schedule(ops, {"M1": day_shifts()}, START, at(120), split=False)
		self.assertEqual(result.slots, [])
		self.assertEqual([u.key for u in result.unscheduled], ["big", "next"])
		self.assertIn("waits on", result.unscheduled[1].reason)

	def test_blocked_time_is_skipped(self):
		calendar = subtract(day_shifts(), [(at(1), at(3))])
		ops = [op("a", "A", 10, {"M1": (0, 120)})]
		slot = schedule(ops, {"M1": calendar}, START, at(120)).slots[0]
		self.assertEqual(slot.end, at(4))

	def test_release_date_holds_the_start(self):
		ops = [op("a", "A", 10, {"M1": (0, 60)}, release=at(5))]
		self.assertEqual(schedule(ops, {"M1": day_shifts()}, START, at(120)).slots[0].start, at(5))

	def test_shared_setup_group_skips_the_second_setup(self):
		ops = [
			op("a", "A", 10, {"M1": (30, 60)}, setup_group="red", order=0),
			op("b", "B", 10, {"M1": (30, 60)}, setup_group="red", order=1),
			op("c", "C", 10, {"M1": (30, 60)}, setup_group="blue", order=2),
		]
		slots = {s.key: s for s in schedule(ops, {"M1": day_shifts()}, START, at(120), rule="FIFO").slots}
		self.assertFalse(slots["a"].setup_skipped)
		self.assertTrue(slots["b"].setup_skipped)
		self.assertEqual(slots["b"].end, at(2.5))
		self.assertFalse(slots["c"].setup_skipped)

	def test_pinned_operation_goes_first_on_its_machine(self):
		ops = [
			op("urgent", "A", 10, {"M1": (0, 60)}, due=at(1)),
			op("running", "B", 20, {"M1": (0, 30)}, pinned_machine="M1", due=at(100)),
			op("before", "B", 10, {"M1": (0, 30)}),
		]
		result = schedule(ops, {"M1": day_shifts()}, START, at(120))
		self.assertEqual(result.slots[0].key, "running")
		self.assertEqual(result.slots[0].start, START)

	def test_no_eligible_machine(self):
		result = schedule([op("a", "A", 10, {})], {"M1": day_shifts()}, START, at(120))
		self.assertEqual(result.unscheduled[0].reason, "no eligible machine")

	def test_kpis(self):
		ops = [
			op("a", "A", 10, {"M1": (0, 240)}, due=at(2)),
			op("b", "B", 10, {"M1": (0, 60)}, due=at(100)),
		]
		result = schedule(ops, {"M1": day_shifts(days=1)}, START, at(24), rule="FIFO")
		k = result.kpis
		self.assertEqual(k["late_jobs"], ["A"])
		self.assertAlmostEqual(k["total_tardiness_minutes"], 120)
		self.assertEqual(k["makespan_end"], at(5))
		self.assertAlmostEqual(k["machine_load"]["M1"]["utilisation"], 62.5)

	def test_bad_input(self):
		with self.assertRaises(ValueError):
			schedule([], {}, START, START)
		with self.assertRaises(ValueError):
			schedule([], {}, START, at(1), rule="Random")
		with self.assertRaises(ValueError):
			schedule([op("a", "A", 1, {}), op("a", "B", 1, {})], {}, START, at(1))


class TestFollowingThePlan(unittest.TestCase):
	def slot(self, name, start, end):
		return {"name": name, "job": "WO-1", "operation": "Cut", "start": start, "end": end}

	def test_current_and_next(self):
		slots = [self.slot("s3", at(4), at(5)), self.slot("s1", at(0), at(2)), self.slot("s2", at(2), at(4))]
		view = current_and_next(slots, at(1), upcoming=1)
		self.assertEqual(view["current"]["name"], "s1")
		self.assertEqual([s["name"] for s in view["next"]], ["s2"])

	def test_behind_schedule(self):
		current = self.slot("s1", at(0), at(2))
		machines = [
			{"name": "M1", "status": "Down", "schedule": {"current": current}},
			{"name": "M2", "status": "Running", "schedule": {"current": current}},
			{"name": "M3", "status": "Idle", "schedule": {"current": None}},
		]
		found = behind_schedule_findings(machines, at(0.5))
		self.assertEqual([f["evidence"]["machine"] for f in found], ["M1"])
		self.assertEqual(found[0]["rule_key"], "schedule:s1:behind")
		self.assertEqual(behind_schedule_findings(machines, at(0.1)), [])


if __name__ == "__main__":
	unittest.main()
