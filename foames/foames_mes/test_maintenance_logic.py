# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Preventive maintenance arithmetic: status bands, due dates and the suggestions. No Frappe site needed."""

import unittest
from datetime import datetime, timedelta

from foames.foames_mes.maintenance import (
	SEVERITY,
	assess,
	calendar_days,
	findings,
	projected_due,
	rule_key,
)

SINCE = datetime(2026, 10, 1, 8, 0, 0)


def plan(status, **overrides):
	values = {
		"name": "MPL-00001",
		"title": "Grease spindle",
		"machine": "PRESS-1",
		"trigger": "Run Hours",
		"interval": 500,
		"used": 480,
		"percent": 96,
		"status": status,
		"since": SINCE,
	}
	values.update(overrides)
	return values


class TestAssess(unittest.TestCase):
	def test_bands(self):
		self.assertEqual(assess(0, 100)["status"], "OK")
		self.assertEqual(assess(89.99, 100)["status"], "OK")
		self.assertEqual(assess(90, 100)["status"], "Due Soon")
		self.assertEqual(assess(99.99, 100)["status"], "Due Soon")
		self.assertEqual(assess(100, 100)["status"], "Due")
		self.assertEqual(assess(109.99, 100)["status"], "Due")
		self.assertEqual(assess(110, 100)["status"], "Overdue")

	def test_custom_thresholds(self):
		self.assertEqual(assess(70, 100, warn_percent=70)["status"], "Due Soon")
		self.assertEqual(assess(100, 100, grace_percent=0)["status"], "Overdue")

	def test_missing_thresholds_use_defaults(self):
		self.assertEqual(assess(90, 100, None, None)["status"], "Due Soon")
		self.assertEqual(assess(110, 100, None, None)["status"], "Overdue")

	def test_percent_and_remaining(self):
		result = assess(250, 1000)
		self.assertAlmostEqual(result["percent"], 25.0)
		self.assertAlmostEqual(result["remaining"], 750.0)
		self.assertAlmostEqual(assess(1200, 1000)["remaining"], -200.0)

	def test_negative_usage_is_zero(self):
		self.assertEqual(assess(-5, 100)["percent"], 0.0)
		self.assertEqual(assess(None, 100)["status"], "OK")

	def test_interval_must_be_positive(self):
		for interval in (0, -1, None):
			with self.assertRaises(ValueError):
				assess(1, interval)


class TestProjectedDue(unittest.TestCase):
	def test_calendar_is_exact(self):
		now = SINCE + timedelta(days=3)
		self.assertEqual(projected_due(3, 30, SINCE, now, "Calendar"), SINCE + timedelta(days=30))

	def test_usage_projects_at_the_average_rate(self):
		# 100 hours used in 10 days: the remaining 400 take another 40 days.
		now = SINCE + timedelta(days=10)
		self.assertEqual(projected_due(100, 500, SINCE, now, "Run Hours"), now + timedelta(days=40))

	def test_no_usage_means_no_projection(self):
		now = SINCE + timedelta(days=10)
		self.assertIsNone(projected_due(0, 500, SINCE, now, "Count"))
		self.assertIsNone(projected_due(10, 500, SINCE, SINCE, "Count"))

	def test_used_up_is_due_now(self):
		now = SINCE + timedelta(days=10)
		self.assertEqual(projected_due(600, 500, SINCE, now, "Count"), now)

	def test_calendar_days(self):
		self.assertAlmostEqual(calendar_days(SINCE, SINCE + timedelta(hours=36)), 1.5)
		self.assertEqual(calendar_days(SINCE, SINCE - timedelta(hours=1)), 0.0)


class TestFindings(unittest.TestCase):
	def test_ok_plans_raise_nothing(self):
		self.assertEqual(findings([plan("OK")]), [])

	def test_severity_follows_status(self):
		for status, severity in SEVERITY.items():
			(finding,) = findings([plan(status)])
			self.assertEqual(finding["severity"], severity)
			self.assertEqual(finding["category"], "Maintenance")
			self.assertEqual(
				(finding["reference_doctype"], finding["reference_name"]), ("Maintenance Plan", "MPL-00001")
			)
			self.assertIn(status.lower(), finding["title"])
			self.assertLessEqual(len(finding["title"]), 140)

	def test_key_is_per_cycle_and_status(self):
		(due_soon,) = findings([plan("Due Soon")])
		(due,) = findings([plan("Due")])
		(next_cycle,) = findings([plan("Due", since=SINCE + timedelta(days=60))])
		self.assertNotEqual(due_soon["rule_key"], due["rule_key"])
		self.assertNotEqual(due["rule_key"], next_cycle["rule_key"])
		self.assertEqual(due["rule_key"], rule_key("MPL-00001", SINCE, "Due"))

	def test_wording_names_the_meter_and_the_work_order(self):
		(finding,) = findings([plan("Due", used=510, percent=102, open_work_order="MWO-2026-00001")])
		self.assertIn("510.0 of 500.0 run hours", finding["suggestion"])
		self.assertIn("MWO-2026-00001", finding["suggestion"])
		self.assertEqual(finding["evidence"]["open_work_order"], "MWO-2026-00001")
		(finding,) = findings([plan("Due")])
		self.assertIn("Create a Maintenance Work Order", finding["suggestion"])

	def test_due_soon_names_the_projected_date(self):
		(finding,) = findings([plan("Due Soon", due_on=datetime(2026, 11, 20, 8, 0))])
		self.assertIn("2026-11-20", finding["suggestion"])
		self.assertEqual(finding["evidence"]["due_on"], "2026-11-20 08:00:00")


if __name__ == "__main__":
	unittest.main()
