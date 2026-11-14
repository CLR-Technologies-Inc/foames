# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Production Schedule on a site: building from shift windows and cycle times, maintenance blocks,
a machine that keeps the job it is running, publishing, the floor snapshot and the behind-schedule
rule."""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from foames.foames_mes.doctype.production_schedule.production_schedule import (
	behind_schedule,
	get_machine_schedule,
)
from foames.foames_mes.floor import floor_snapshot
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import extra_hooks, make_machine, make_reason

MONDAY = "2026-11-16"
WINDOW = {"shift_start": "06:00:00", "scheduled_minutes_per_day": 480}


def at(time, day=MONDAY):
	return get_datetime(f"{day} {time}")


def make_schedule(rows, **overrides):
	values = {
		"doctype": "Production Schedule",
		"schedule_start": at("06:00:00"),
		"horizon_days": 5,
		"dispatch_rule": "EDD",
		"line": "T-SCHED",
		"jobs": rows,
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def operations(schedule):
	return {
		(r.job, r.sequence): r
		for r in frappe.get_all(
			"Scheduled Operation",
			filters={"production_schedule": schedule},
			fields=["*"],
		)
	}


def seconds_per_unit(row, machine):
	return 6 if row.get("job") == "EST" else None


class TestProductionSchedule(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-SCHED-1", line="T-SCHED", machine_type="Press", ideal_cycle_seconds=30, **WINDOW)
		make_machine("T-SCHED-2", line="T-SCHED", machine_type="Lathe", ideal_cycle_seconds=60, **WINDOW)

	def test_build_places_operations_in_sequence_inside_the_shift(self):
		schedule = make_schedule(
			[
				{
					"job": "WO-A",
					"operation": "Press",
					"sequence": 10,
					"quantity": 120,
					"machine_type": "Press",
				},
				{"job": "WO-A", "operation": "Turn", "sequence": 20, "quantity": 60, "machine_type": "Lathe"},
			]
		)
		result = schedule.build()
		self.assertEqual(result["scheduled"], 2)
		ops = operations(schedule.name)
		press, turn = ops[("WO-A", 10)], ops[("WO-A", 20)]
		self.assertEqual(press.machine, "T-SCHED-1")
		# 120 units at 30 seconds on the press, then 60 units at 60 seconds on the lathe.
		self.assertEqual(get_datetime(press.end_time), at("07:00:00"))
		self.assertEqual(get_datetime(turn.start_time), at("07:00:00"))
		self.assertEqual(get_datetime(turn.end_time), at("08:00:00"))
		schedule.reload()
		self.assertEqual(schedule.operations_scheduled, 2)
		self.assertTrue(schedule.built_on)

	def test_work_longer_than_the_shift_continues_next_day(self):
		schedule = make_schedule(
			[{"job": "BIG", "sequence": 10, "run_minutes": 600, "machines": "T-SCHED-1"}]
		)
		schedule.build()
		op = operations(schedule.name)[("BIG", 10)]
		self.assertEqual(get_datetime(op.end_time), at("08:00:00", "2026-11-17"))
		self.assertTrue(op.split)

	def test_late_and_unscheduled(self):
		schedule = make_schedule(
			[
				{
					"job": "LATE",
					"sequence": 10,
					"run_minutes": 120,
					"machines": "T-SCHED-2",
					"due_date": at("07:00:00"),
				},
				{"job": "NONE", "sequence": 10, "quantity": 5, "machine_type": "Oven"},
			]
		)
		result = schedule.build()
		ops = operations(schedule.name)
		self.assertEqual(ops[("LATE", 10)].status, "Late")
		self.assertAlmostEqual(ops[("LATE", 10)].lateness_minutes, 60)
		self.assertEqual(ops[("NONE", 10)].status, "Unscheduled")
		self.assertEqual(result["late_jobs"], ["LATE"])

	def test_maintenance_blocks_the_machine(self):
		reason = make_reason("T-SCHED-PM", category="Planned", counts_as_planned=1).name
		plan = frappe.get_doc(
			{
				"doctype": "Maintenance Plan",
				"title": "Change the die",
				"machine": "T-SCHED-1",
				"trigger_type": "Calendar",
				"interval": 30,
				"estimated_minutes": 120,
				"downtime_reason": reason,
			}
		).insert()
		frappe.get_doc(
			{"doctype": "Maintenance Work Order", "maintenance_plan": plan.name, "due_on": at("06:00:00")}
		).insert()
		schedule = make_schedule(
			[{"job": "WO-M", "sequence": 10, "run_minutes": 60, "machines": "T-SCHED-1"}]
		)
		schedule.build()
		self.assertEqual(get_datetime(operations(schedule.name)[("WO-M", 10)].start_time), at("08:00:00"))

	def test_cycle_time_estimator_hook(self):
		with extra_hooks(
			foames_cycle_time_estimators=[
				"foames.foames_mes.doctype.production_schedule.test_production_schedule.seconds_per_unit"
			]
		):
			schedule = make_schedule(
				[{"job": "EST", "sequence": 10, "quantity": 100, "machines": "T-SCHED-1"}]
			)
			schedule.build()
		self.assertAlmostEqual(operations(schedule.name)[("EST", 10)].run_minutes, 10)

	def test_running_job_stays_on_its_machine(self):
		reference = frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "ERPNext",
				"reference_type": "Job Card",
				"external_id": "T-SCHED-JC",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Machine", "T-SCHED-2", "current_job_reference", reference.name)
		schedule = make_schedule(
			[
				{
					"job": "OTHER",
					"sequence": 10,
					"run_minutes": 30,
					"machines": "T-SCHED-2",
					"due_date": at("06:30:00"),
				},
				{
					"job": "RUN",
					"sequence": 10,
					"run_minutes": 30,
					"machines": "T-SCHED-1",
					"job_reference": reference.name,
				},
			]
		)
		schedule.build()
		ops = operations(schedule.name)
		self.assertEqual(ops[("RUN", 10)].machine, "T-SCHED-2")
		self.assertEqual(get_datetime(ops[("RUN", 10)].start_time), at("06:00:00"))

	def test_publish_supersedes_and_feeds_the_floor(self):
		now = now_datetime()
		first = make_schedule(
			[{"job": "P1", "sequence": 10, "run_minutes": 60, "machines": "T-SCHED-1"}],
			schedule_start=add_to_date(now, hours=-2),
		)
		with self.assertRaises(frappe.ValidationError):
			first.publish()
		first.build()
		first.publish()
		second = make_schedule(
			[{"job": "P2", "sequence": 10, "run_minutes": 24 * 60, "machines": "T-SCHED-1"}],
			schedule_start=add_to_date(now, hours=-1),
			allow_split=1,
		)
		# A machine with the whole day as its window, so "now" is always inside it.
		frappe.db.set_value("Machine", "T-SCHED-1", {"shift_start": None, "scheduled_minutes_per_day": 0})
		second.build()
		second.publish()
		self.assertEqual(frappe.db.get_value("Production Schedule", first.name, "status"), "Superseded")
		with self.assertRaises(frappe.ValidationError):
			second.build()

		frappe.db.set_value("Machine", "T-SCHED-1", "status", "Down")
		snapshot = floor_snapshot()
		machine = next(m for m in snapshot["machines"] if m["name"] == "T-SCHED-1")
		self.assertEqual(machine["schedule"]["current"]["job"], "P2")
		found = behind_schedule(snapshot)
		self.assertTrue(any(f["evidence"]["machine"] == "T-SCHED-1" for f in found))
		self.assertTrue(any(s["job"] == "P2" for s in get_machine_schedule("T-SCHED-1")))

		copy = frappe.get_doc("Production Schedule", second.copy_to_draft())
		self.assertEqual(copy.status, "Draft")
		self.assertEqual(len(copy.jobs), 1)

	def test_validation(self):
		with self.assertRaises(frappe.ValidationError):
			make_schedule([{"job": "X", "machines": "NO-SUCH-MACHINE"}])
		with self.assertRaises(frappe.ValidationError):
			make_schedule([], horizon_days=0)

	def test_deleting_a_schedule_removes_its_operations(self):
		schedule = make_schedule([{"job": "DEL", "sequence": 10, "run_minutes": 30, "machines": "T-SCHED-1"}])
		schedule.build()
		frappe.delete_doc("Production Schedule", schedule.name)
		self.assertFalse(frappe.db.exists("Scheduled Operation", {"production_schedule": schedule.name}))
