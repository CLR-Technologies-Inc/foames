# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Andon response times and escalation, without a site."""

import unittest
from datetime import datetime

from foames.foames_mes.andon import allowed_transition, minutes_between, overdue_andon_calls


def call(minutes_open, status="Open", **extra):
	values = {
		"name": "ANDON-1",
		"machine": "press-1",
		"call_type": "Maintenance",
		"status": status,
		"minutes_open": minutes_open,
		"acknowledge_within_minutes": 5,
		"resolve_within_minutes": 30,
	}
	values.update(extra)
	return values


class TestTransitions(unittest.TestCase):
	def test_forward_only(self):
		self.assertTrue(allowed_transition(None, "Open"))
		self.assertTrue(allowed_transition("Open", "Acknowledged"))
		self.assertTrue(allowed_transition("Open", "Resolved"))
		self.assertTrue(allowed_transition("Acknowledged", "Resolved"))
		self.assertTrue(allowed_transition("Acknowledged", "Cancelled"))
		self.assertFalse(allowed_transition("Acknowledged", "Open"))
		self.assertFalse(allowed_transition("Resolved", "Open"))
		self.assertFalse(allowed_transition("Cancelled", "Acknowledged"))
		self.assertTrue(allowed_transition("Resolved", "Resolved"))

	def test_minutes(self):
		self.assertEqual(minutes_between(datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 8, 7, 30)), 7.5)
		self.assertIsNone(minutes_between(None, datetime(2026, 1, 1)))
		self.assertEqual(minutes_between(datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 8)), 0)


class TestEscalation(unittest.TestCase):
	def keys(self, *calls):
		return [s["rule_key"] for s in overdue_andon_calls({"andon_calls": list(calls)})]

	def test_within_targets_nothing(self):
		self.assertEqual(self.keys(call(4)), [])

	def test_unanswered(self):
		self.assertEqual(self.keys(call(5)), ["andon:ANDON-1:acknowledge"])

	def test_acknowledged_but_not_resolved(self):
		self.assertEqual(self.keys(call(10, "Acknowledged")), [])
		self.assertEqual(self.keys(call(31, "Acknowledged")), ["andon:ANDON-1:resolve"])

	def test_both_targets_missed(self):
		self.assertEqual(self.keys(call(45)), ["andon:ANDON-1:acknowledge", "andon:ANDON-1:resolve"])

	def test_already_escalated_is_not_raised_again(self):
		self.assertEqual(self.keys(call(45, ack_escalated=1, resolve_escalated=1)), [])
		self.assertEqual(self.keys(call(45, ack_escalated=1)), ["andon:ANDON-1:resolve"])

	def test_closed_calls_and_zero_targets(self):
		self.assertEqual(self.keys(call(90, "Resolved"), call(90, "Cancelled")), [])
		self.assertEqual(self.keys(call(90, acknowledge_within_minutes=0, resolve_within_minutes=0)), [])

	def test_severity_and_reference(self):
		(finding,) = overdue_andon_calls(
			{"andon_calls": [call(3, escalation_severity="Critical", acknowledge_within_minutes=2)]}
		)
		self.assertEqual(finding["severity"], "Critical")
		self.assertEqual((finding["reference_doctype"], finding["reference_name"]), ("Andon Call", "ANDON-1"))
		self.assertEqual(finding["category"], "Andon")


if __name__ == "__main__":
	unittest.main()
