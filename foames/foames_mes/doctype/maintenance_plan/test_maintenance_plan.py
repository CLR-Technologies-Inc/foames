# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, add_to_date, get_datetime, now_datetime

from foames.foames_mes.api import record_events
from foames.foames_mes.doctype.maintenance_plan.maintenance_plan import (
	check_maintenance_plans,
	make_work_order,
)
from foames.foames_mes.report.maintenance_due_list.maintenance_due_list import execute as due_list
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_reason, make_user

DAY = "2026-10-20"


def at(time):
	return get_datetime(f"{DAY} {time}")


def make_plan(machine="T-PM", **overrides):
	values = {
		"doctype": "Maintenance Plan",
		"title": "Grease the spindle",
		"machine": machine,
		"trigger_type": "Calendar",
		"interval": 30,
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


class TestMaintenancePlan(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-PM")
		make_machine("T-PM2", line="T-LINE-PM")

	# The meters

	def test_new_plan_starts_counting_now(self):
		plan = make_plan()
		self.assertIsNotNone(plan.last_done_on)
		self.assertEqual(plan.status, "OK")
		self.assertLess(plan.used, 0.01)

	def test_calendar_plan_bands(self):
		now = now_datetime()
		self.assertEqual(make_plan(last_done_on=add_days(now, -10)).status, "OK")
		self.assertEqual(make_plan(last_done_on=add_days(now, -28)).status, "Due Soon")
		self.assertEqual(make_plan(last_done_on=add_days(now, -31)).status, "Due")
		overdue = make_plan(last_done_on=add_days(now, -40))
		self.assertEqual(overdue.status, "Overdue")
		self.assertEqual(get_datetime(overdue.due_on), get_datetime(add_days(overdue.last_done_on, 30)))

	def test_invalid_plans_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_plan(interval=0)
		with self.assertRaises(frappe.ValidationError):
			make_plan(warn_percent=120)
		with self.assertRaises(frappe.ValidationError):
			make_plan(last_done_on=add_days(now_datetime(), 1))

	def test_run_hours_come_from_the_state_ledger(self):
		# Running 08:00-10:00, Down 10:00-10:30, Running 10:30-12:00, Idle after: 3.5 run hours by 13:00.
		record_events(
			[
				{"machine": "T-PM", "type": "State", "state": "Running", "timestamp": f"{DAY}T08:00:00"},
				{"machine": "T-PM", "type": "State", "state": "Down", "timestamp": f"{DAY}T10:00:00"},
				{"machine": "T-PM", "type": "State", "state": "Running", "timestamp": f"{DAY}T10:30:00"},
				{"machine": "T-PM", "type": "State", "state": "Idle", "timestamp": f"{DAY}T12:00:00"},
			]
		)
		plan = make_plan(trigger_type="Run Hours", interval=3.8, last_done_on=at("07:00:00"))
		meter = plan.measure(at("13:00:00"))
		self.assertAlmostEqual(meter["used"], 3.5, places=6)
		self.assertEqual(meter["status"], "Due Soon")
		# Not measured from before the last service.
		plan.last_done_on = at("11:00:00")
		self.assertAlmostEqual(plan.measure(at("13:00:00"))["used"], 1.0, places=6)

	def test_counts_come_from_counter_deltas(self):
		record_events(
			[
				{"machine": "T-PM", "type": "Count", "value": 100, "timestamp": f"{DAY}T08:00:00"},
				{"machine": "T-PM", "type": "Count", "value": 400, "timestamp": f"{DAY}T09:00:00"},
				{
					"machine": "T-PM",
					"type": "Count",
					"counter": "scrap",
					"value": 0,
					"timestamp": f"{DAY}T08:00:00",
				},
				{
					"machine": "T-PM",
					"type": "Count",
					"counter": "scrap",
					"value": 20,
					"timestamp": f"{DAY}T09:00:00",
				},
				# A reset never counts as production.
				{"machine": "T-PM", "type": "Count", "value": 5, "timestamp": f"{DAY}T10:00:00"},
				{
					"machine": "T-PM",
					"type": "Count",
					"counter": "strokes",
					"value": 0,
					"timestamp": f"{DAY}T08:00:00",
				},
				{
					"machine": "T-PM",
					"type": "Count",
					"counter": "strokes",
					"value": 900,
					"timestamp": f"{DAY}T09:00:00",
				},
			]
		)
		output = make_plan(trigger_type="Count", interval=1000, last_done_on=at("07:00:00"))
		self.assertAlmostEqual(output.measure(at("11:00:00"))["used"], 320)
		strokes = make_plan(
			trigger_type="Count", interval=1000, counter_name=" Strokes ", last_done_on=at("07:00:00")
		)
		self.assertEqual(strokes.counter_name, "strokes")
		meter = strokes.measure(at("11:00:00"))
		self.assertAlmostEqual(meter["used"], 900)
		self.assertEqual(meter["status"], "Due Soon")

	def test_counter_is_cleared_for_other_triggers(self):
		self.assertIsNone(make_plan(counter_name="strokes").counter_name)

	# Suggestions and work orders

	def test_check_raises_one_suggestion_per_status_and_cycle(self):
		plan = make_plan(last_done_on=add_days(now_datetime(), -31))
		first = check_maintenance_plans()
		self.assertEqual(len(first), 1)
		suggestion = frappe.get_doc("Agent Suggestion", first[0])
		self.assertEqual((suggestion.category, suggestion.severity), ("Maintenance", "Warning"))
		self.assertEqual(
			(suggestion.reference_doctype, suggestion.reference_name), ("Maintenance Plan", plan.name)
		)
		self.assertEqual(check_maintenance_plans(), [])
		self.assertEqual(frappe.db.get_value("Maintenance Plan", plan.name, "status"), "Due")

	def test_disabled_plans_are_skipped(self):
		make_plan(last_done_on=add_days(now_datetime(), -31), disabled=1)
		self.assertEqual(check_maintenance_plans(), [])

	def test_auto_work_order_is_opened_once(self):
		plan = make_plan(last_done_on=add_days(now_datetime(), -31), auto_create_work_order=1)
		check_maintenance_plans()
		check_maintenance_plans()
		orders = frappe.get_all(
			"Maintenance Work Order", {"maintenance_plan": plan.name}, ["name", "plan_status_at_raise"]
		)
		self.assertEqual(len(orders), 1)
		self.assertEqual(orders[0].plan_status_at_raise, "Due")
		self.assertEqual(
			frappe.db.get_value("Maintenance Plan", plan.name, "open_work_order"), orders[0].name
		)

	def test_completing_a_work_order_restarts_the_meter_and_closes_suggestions(self):
		reason = make_reason("T-PM-PLANNED", category="Planned", counts_as_planned=1)
		plan = make_plan(last_done_on=add_days(now_datetime(), -31), downtime_reason=reason.name)
		(suggestion,) = check_maintenance_plans()
		order = frappe.get_doc("Maintenance Work Order", make_work_order(plan.name))
		self.assertEqual(order.machine, "T-PM")
		self.assertEqual(order.title, plan.title)
		self.assertEqual(make_work_order(plan.name), order.name)

		start = add_to_date(now_datetime(), hours=-2)
		order.started_on = start
		order.status = "In Progress"
		order.save()
		downtime = frappe.get_doc("Downtime Record", order.downtime_record)
		self.assertEqual((downtime.status, downtime.reason), ("Open", reason.name))

		done = add_to_date(now_datetime(), hours=-1)
		order.completed_on = done
		order.status = "Completed"
		order.save()
		self.assertAlmostEqual(order.actual_minutes, 60, places=3)
		self.assertEqual(order.completed_by, frappe.session.user)
		downtime.reload()
		self.assertEqual(downtime.status, "Closed")
		self.assertAlmostEqual(downtime.duration_minutes, 60, places=3)

		plan.reload()
		self.assertLess(abs((get_datetime(plan.last_done_on) - get_datetime(done)).total_seconds()), 1)
		self.assertEqual(plan.last_work_order, order.name)
		self.assertEqual(plan.status, "OK")
		self.assertIsNone(plan.open_work_order)
		self.assertEqual(frappe.db.get_value("Agent Suggestion", suggestion, "status"), "Done")

		order.status = "Open"
		with self.assertRaises(frappe.ValidationError):
			order.save()

	def test_completing_without_starting_records_a_closed_stop(self):
		reason = make_reason("T-PM-PLANNED", category="Planned", counts_as_planned=1)
		plan = make_plan(last_done_on=add_days(now_datetime(), -31), downtime_reason=reason.name)
		order = frappe.get_doc(
			{
				"doctype": "Maintenance Work Order",
				"maintenance_plan": plan.name,
				"status": "Completed",
				"started_on": add_to_date(now_datetime(), minutes=-45),
				"completed_on": add_to_date(now_datetime(), minutes=-15),
			}
		).insert()
		downtime = frappe.get_doc("Downtime Record", order.downtime_record)
		self.assertEqual(downtime.status, "Closed")
		self.assertAlmostEqual(downtime.duration_minutes, 30, places=3)

	def test_late_completion_does_not_move_the_meter_back(self):
		plan = make_plan(last_done_on=add_days(now_datetime(), -5))
		frappe.get_doc(
			{
				"doctype": "Maintenance Work Order",
				"maintenance_plan": plan.name,
				"status": "Completed",
				"started_on": add_days(now_datetime(), -21),
				"completed_on": add_days(now_datetime(), -20),
			}
		).insert()
		self.assertEqual(
			get_datetime(frappe.db.get_value("Maintenance Plan", plan.name, "last_done_on")),
			get_datetime(plan.last_done_on),
		)

	def test_cancelling_closes_the_stop(self):
		reason = make_reason("T-PM-PLANNED", category="Planned", counts_as_planned=1)
		plan = make_plan(downtime_reason=reason.name)
		order = frappe.get_doc(
			{
				"doctype": "Maintenance Work Order",
				"maintenance_plan": plan.name,
				"status": "In Progress",
				"started_on": add_to_date(now_datetime(), minutes=-10),
			}
		).insert()
		order.status = "Cancelled"
		order.save()
		self.assertEqual(frappe.db.get_value("Downtime Record", order.downtime_record, "status"), "Closed")
		self.assertIsNone(frappe.db.get_value("Maintenance Plan", plan.name, "open_work_order"))

	# The due list and the role

	def test_due_list_orders_worst_first_and_filters(self):
		now = now_datetime()
		ok = make_plan(last_done_on=add_days(now, -1))
		soon = make_plan(last_done_on=add_days(now, -28))
		overdue = make_plan(machine="T-PM2", last_done_on=add_days(now, -40))
		_columns, rows, _msg, chart, summary = due_list({})
		names = [r["maintenance_plan"] for r in rows]
		self.assertNotIn(ok.name, names)
		self.assertLess(names.index(overdue.name), names.index(soon.name))
		self.assertEqual(summary[0]["value"], sum(1 for r in rows if r["status"] == "Overdue"))
		self.assertIsNotNone(chart)

		_columns, rows, *_ = due_list({"show": "All plans", "machine": "T-PM"})
		self.assertIn(ok.name, [r["maintenance_plan"] for r in rows])
		self.assertTrue(all(r["machine"] == "T-PM" for r in rows))

		_columns, rows, *_ = due_list({"line": "T-LINE-PM"})
		self.assertEqual([r["maintenance_plan"] for r in rows], [overdue.name])

		_columns, rows, *_ = due_list({"show": "Due or Overdue", "horizon_days": 5, "machine": "T-PM"})
		self.assertIn(soon.name, [r["maintenance_plan"] for r in rows])
		self.assertNotIn(ok.name, [r["maintenance_plan"] for r in rows])

	def test_maintenance_role_owns_plans_and_operators_only_read(self):
		maintainer = make_user("t-pm-maint@example.com", "FoaMES Maintenance").name
		operator = make_user("t-pm-operator@example.com", "FoaMES Operator").name
		plan = make_plan(last_done_on=add_days(now_datetime(), -31))
		with as_user(maintainer):
			self.assertTrue(frappe.has_permission("Maintenance Plan", "create"))
			self.assertTrue(frappe.has_permission("Maintenance Work Order", "write"))
			make_work_order(plan.name)
			_columns, rows, *_ = due_list({})
			self.assertIn(plan.name, [r["maintenance_plan"] for r in rows])
		with as_user(operator):
			self.assertTrue(frappe.has_permission("Maintenance Plan", "read"))
			self.assertFalse(frappe.has_permission("Maintenance Plan", "create"))
			self.assertFalse(frappe.has_permission("Maintenance Work Order", "write"))
			with self.assertRaises(frappe.PermissionError):
				make_work_order(plan.name)
