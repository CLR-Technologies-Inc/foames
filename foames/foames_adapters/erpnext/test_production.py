# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Pure tests of the roll-up arithmetic and the production-log posting rule. No site needed."""

import unittest
from datetime import datetime

from foames.foames_adapters.erpnext import postings
from foames.foames_adapters.erpnext.production import production_payload, running_intervals, window_key

T = datetime(2026, 10, 31, 8, 0, 0)


def at(minutes: int) -> datetime:
	return T.replace(hour=8 + minutes // 60, minute=minutes % 60)


class TestRunningIntervals(unittest.TestCase):
	def test_state_carried_in_counts_until_the_first_change(self):
		intervals = running_intervals("Running", [(at(10), "Idle"), (at(20), "Running")], at(0), at(30))
		self.assertEqual(intervals, [(at(0), at(10)), (at(20), at(30))])

	def test_no_state_means_no_run_time(self):
		self.assertEqual(running_intervals(None, [], at(0), at(30)), [])
		self.assertEqual(running_intervals("Idle", [(at(5), "Down")], at(0), at(30)), [])

	def test_events_outside_the_window_are_ignored_but_set_the_state(self):
		events = [(at(0), "Running"), (at(40), "Idle")]
		self.assertEqual(running_intervals("Idle", events, at(0), at(30)), [(at(0), at(30))])

	def test_repeated_running_states_merge(self):
		events = [(at(5), "Running"), (at(15), "Running"), (at(25), "Idle")]
		self.assertEqual(
			running_intervals("Idle", events, at(0), at(30)), [(at(5), at(15)), (at(15), at(25))]
		)


class TestProductionPayload(unittest.TestCase):
	def test_nothing_to_report_queues_nothing(self):
		self.assertIsNone(production_payload("PO-JOB-1", at(0), at(10), {}, [], "M1"))
		self.assertIsNone(production_payload("PO-JOB-1", at(0), at(10), {"good": 0, "temp": 5}, [], "M1"))

	def test_counts_and_run_stretches(self):
		payload = production_payload(
			"PO-JOB-1", at(0), at(30), {"good": 12, "scrap": 1, "reject": 1}, [(at(5), at(25))], "M1"
		)
		self.assertEqual(payload["completed_qty"], 12)
		self.assertEqual(payload["process_loss_qty"], 2)
		self.assertEqual(payload["run_intervals"], [["2026-10-31 08:05:00", "2026-10-31 08:25:00"]])
		self.assertEqual(
			(payload["from_time"], payload["to_time"]), ("2026-10-31 08:00:00", "2026-10-31 08:30:00")
		)
		self.assertIn("20.0 min running", payload["remarks"])
		# What the window builds is a valid posting.
		prepared = postings.prepare(postings.OPERATIONS["Job Card Production Log"], payload)
		self.assertEqual(prepared["completed_qty"], 12.0)

	def test_run_time_alone_is_reported(self):
		payload = production_payload("PO-JOB-1", at(0), at(30), {}, [(at(0), at(30))], "M1")
		self.assertEqual(payload["completed_qty"], 0)
		self.assertEqual(len(payload["run_intervals"]), 1)

	def test_window_key_names_the_window(self):
		self.assertEqual(window_key("PO-JOB-1", "M1", at(30)), "PO-JOB-1:M1:production:2026-10-31 08:30:00")


class TestProductionLogRule(unittest.TestCase):
	def prepare(self, payload):
		return postings.prepare(postings.OPERATIONS["Job Card Production Log"], payload)

	def test_window_must_run_forwards(self):
		with self.assertRaisesRegex(ValueError, "from_time before to_time"):
			self.prepare(
				{"job_card": "PO-JOB-1", "from_time": "2026-10-31 09:00:00", "to_time": "2026-10-31 08:00:00"}
			)

	def test_intervals_are_pairs(self):
		base = {"job_card": "PO-JOB-1", "from_time": "2026-10-31 08:00:00", "to_time": "2026-10-31 09:00:00"}
		with self.assertRaisesRegex(ValueError, "run_intervals"):
			self.prepare({**base, "run_intervals": [["2026-10-31 08:00:00"]]})
		with self.assertRaisesRegex(ValueError, "run_intervals"):
			self.prepare({**base, "run_intervals": "08:00-09:00"})
		prepared = self.prepare({**base, "run_intervals": [("2026-10-31 08:00:00", "2026-10-31 08:30:00")]})
		self.assertEqual(prepared["run_intervals"], [["2026-10-31 08:00:00", "2026-10-31 08:30:00"]])
		with self.assertRaisesRegex(ValueError, "cannot be negative"):
			self.prepare({**base, "process_loss_qty": -1})


if __name__ == "__main__":
	unittest.main()
