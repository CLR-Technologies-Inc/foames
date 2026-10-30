# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe

from foames.foames_mes.api import record_events, run_suggestion_rules
from foames.foames_mes.doctype.oee_period.oee_period import compute_daily_oee, get_oee
from foames.tests_compat import IntegrationTestCase


def make_machine(code="T-PRESS", **overrides):
	if frappe.db.exists("Machine", code):
		return frappe.get_doc("Machine", code)
	values = {"doctype": "Machine", "code": code, "counter_rollover": 0}
	values.update(overrides)
	return frappe.get_doc(values).insert()


class TestOEEPeriod(IntegrationTestCase):
	def setUp(self):
		make_machine("T-OEE", ideal_cycle_seconds=60, scheduled_minutes_per_day=480)
		if not frappe.db.exists("Downtime Reason", "T-PM"):
			frappe.get_doc({"doctype": "Downtime Reason", "code": "T-PM", "category": "Planned"}).insert()

	def test_period_from_events_and_downtime(self):
		# 08:00 running, 10:00 down (planned maintenance), 10:30 running, 12:00 idle; counts 0 -> 120 -> 200.
		record_events(
			[
				{"machine": "T-OEE", "type": "State", "state": "Running", "timestamp": "2026-10-20T08:00:00"},
				{"machine": "T-OEE", "type": "Count", "value": 0, "timestamp": "2026-10-20T08:00:00"},
				{"machine": "T-OEE", "type": "Count", "value": 120, "timestamp": "2026-10-20T10:00:00"},
				{"machine": "T-OEE", "type": "State", "state": "Down", "timestamp": "2026-10-20T10:00:00"},
				{"machine": "T-OEE", "type": "State", "state": "Running", "timestamp": "2026-10-20T10:30:00"},
				{"machine": "T-OEE", "type": "Count", "value": 200, "timestamp": "2026-10-20T12:00:00"},
				{
					"machine": "T-OEE",
					"type": "Count",
					"counter": "scrap",
					"value": 0,
					"timestamp": "2026-10-20T08:00:00",
				},
				{
					"machine": "T-OEE",
					"type": "Count",
					"counter": "scrap",
					"value": 10,
					"timestamp": "2026-10-20T12:00:00",
				},
				{"machine": "T-OEE", "type": "State", "state": "Idle", "timestamp": "2026-10-20T12:00:00"},
			]
		)
		dt = frappe.db.get_value("Downtime Record", {"machine": "T-OEE", "status": "Closed"}, "name")
		frappe.db.set_value("Downtime Record", dt, "reason", "T-PM")
		result = get_oee("T-OEE", "2026-10-20 08:00:00", "2026-10-20 13:00:00", planned_minutes=300)
		self.assertAlmostEqual(result["run_minutes"], 210)
		self.assertAlmostEqual(result["availability"], 210 / 270 * 100, places=3)
		self.assertAlmostEqual(
			result["performance"], 200 / 210 * 100, places=3
		)  # 60 s ideal: 210 units possible, 200 counted
		self.assertAlmostEqual(result["quality"], 190 / 200 * 100, places=3)
		self.assertEqual((result["good_count"], result["scrap_count"]), (200, 10))
		self.assertAlmostEqual(result["unknown_minutes"], 0)

	def test_daily_task_creates_one_period_per_machine(self):
		created = compute_daily_oee("2026-10-21")
		self.assertTrue(any("T-OEE" in n for n in created))
		self.assertEqual(compute_daily_oee("2026-10-21"), [])
		doc = frappe.get_doc("OEE Period", created[0]) if "T-OEE" in created[0] else None
		if doc:
			self.assertEqual(doc.planned_minutes, 480)
			self.assertAlmostEqual(doc.unknown_minutes, 480)  # no signal at all that day


class TestSuggestions(IntegrationTestCase):
	def test_rules_raise_once_and_external_agents_can_post(self):
		from foames.foames_mes.api import post_suggestion

		make_machine("T-SUG", status="Unknown")
		name = post_suggestion(
			"Check the chiller",
			"Downtime",
			"Chiller trips every afternoon.",
			agent="plant-agent",
			reference_doctype="Machine",
			reference_name="T-SUG",
			rule_key="ext:chiller",
		)
		self.assertTrue(name)
		self.assertEqual(
			post_suggestion(
				"Check the chiller", "Downtime", "again", agent="plant-agent", rule_key="ext:chiller"
			),
			name,
		)
		doc = frappe.get_doc("Agent Suggestion", name)
		self.assertEqual((doc.agent, doc.status), ("plant-agent", "Open"))
		doc.status = "Accepted"
		doc.save()
		self.assertTrue(doc.resolved_on)
		self.assertIsInstance(run_suggestion_rules(), list)
