# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from foames.foames_mes.doctype.machine.machine import get_machine_by_source
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import make_machine


class TestMachine(IntegrationTestCase):
	def test_title_and_source_id_default_to_the_code(self):
		machine = make_machine("T-MC-DEFAULTS")
		self.assertEqual((machine.title, machine.source_id), ("T-MC-DEFAULTS", "T-MC-DEFAULTS"))
		self.assertEqual(machine.status, "Unknown")
		self.assertEqual(machine.scheduled_minutes_per_day, 480)

	def test_explicit_title_and_source_id_are_kept(self):
		machine = make_machine("T-MC-NAMED", title="Press 1", source_id="plc-press-1")
		self.assertEqual((machine.title, machine.source_id), ("Press 1", "plc-press-1"))

	def test_source_id_is_unique(self):
		make_machine("T-MC-SRC-A", source_id="shared-source")
		with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
			make_machine("T-MC-SRC-B", source_id="shared-source")

	def test_lookup_by_source_id_then_by_name(self):
		make_machine("T-MC-LOOKUP", source_id="plc-7")
		self.assertEqual(get_machine_by_source("plc-7"), "T-MC-LOOKUP")
		self.assertEqual(get_machine_by_source("T-MC-LOOKUP"), "T-MC-LOOKUP")
		self.assertIsNone(get_machine_by_source("no-such-source"))

	def test_disabled_machines_are_not_found(self):
		make_machine("T-MC-OFF", source_id="plc-off", disabled=1)
		self.assertIsNone(get_machine_by_source("plc-off"))
		self.assertIsNone(get_machine_by_source("T-MC-OFF"))

	def test_workstation_reference_must_be_a_workstation(self):
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		item = frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "ERPNext",
				"reference_type": "Item",
				"external_id": "T-MC-ITEM",
			}
		).insert()
		workstation = frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "ERPNext",
				"reference_type": "Workstation",
				"external_id": "T-MC-WS",
			}
		).insert()
		with self.assertRaises(frappe.ValidationError):
			make_machine("T-MC-BAD-WS", workstation_reference=item.name)
		machine = make_machine("T-MC-GOOD-WS", workstation_reference=workstation.name)
		self.assertEqual(machine.workstation_reference, workstation.name)
		with self.assertRaises(frappe.ValidationError):
			make_machine("T-MC-BAD-LOC", location_reference=workstation.name)


class TestSetState(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.machine = make_machine("T-MC-STATE")
		self.t0 = get_datetime("2026-10-20 08:00:00")

	def at(self, minutes):
		return add_to_date(self.t0, minutes=minutes)

	def open_downtime(self):
		return frappe.get_all("Downtime Record", {"machine": "T-MC-STATE", "status": "Open"}, pluck="name")

	def test_running_to_down_opens_one_downtime(self):
		self.machine.set_state("Running", self.at(0))
		self.machine.set_state("Down", self.at(10))
		self.machine.set_state("Down", self.at(20))  # a repeated Down does not open a second one
		self.assertEqual(len(self.open_downtime()), 1)
		self.assertEqual(frappe.db.get_value("Machine", "T-MC-STATE", "status"), "Down")
		self.assertEqual(get_datetime(frappe.db.get_value("Machine", "T-MC-STATE", "last_seen")), self.at(20))
		record = frappe.get_doc("Downtime Record", self.open_downtime()[0])
		self.assertEqual((get_datetime(record.start_time), record.source), (self.at(10), "Automatic"))

	def test_any_other_state_closes_the_downtime(self):
		for state in ("Running", "Idle", "Setup", "Unknown"):
			self.machine.set_state("Down", self.at(0))
			self.machine.set_state(state, self.at(30))
			self.assertEqual(self.open_downtime(), [], state)
			closed = frappe.get_all(
				"Downtime Record",
				{"machine": "T-MC-STATE", "status": "Closed"},
				["duration_minutes"],
				order_by="creation desc",
				limit_page_length=1,
			)
			self.assertEqual(closed[0].duration_minutes, 30)

	def test_states_other_than_down_leave_downtime_alone(self):
		self.machine.set_state("Running", self.at(0))
		self.machine.set_state("Idle", self.at(5))
		self.machine.set_state("Setup", self.at(10))
		self.assertEqual(frappe.db.count("Downtime Record", {"machine": "T-MC-STATE"}), 0)

	def test_state_change_is_written_without_saving_the_document(self):
		self.machine.set_state("Idle", self.at(0))
		fresh = frappe.get_doc("Machine", "T-MC-STATE")
		self.assertEqual((fresh.status, get_datetime(fresh.last_seen)), ("Idle", self.at(0)))


class TestStaleMachines(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("Machine Data Settings", "stale_after_minutes", 15)

	def seen(self, code, minutes_ago, status, **overrides):
		machine = make_machine(code, **overrides)
		machine.db_set(
			{"status": status, "last_seen": add_to_date(now_datetime(), minutes=-minutes_ago)},
			update_modified=False,
		)
		return machine

	def test_silent_running_machine_becomes_unknown(self):
		from foames.foames_mes.tasks import mark_stale_machines_unknown

		self.seen("T-STALE-RUN", 30, "Running")
		self.seen("T-STALE-FRESH", 5, "Running")
		self.seen("T-STALE-DOWN", 60, "Down")
		self.seen("T-STALE-IDLE", 60, "Idle")
		self.seen("T-STALE-OFF", 60, "Running", disabled=1)
		stale = mark_stale_machines_unknown()
		self.assertIn("T-STALE-RUN", stale)
		self.assertIn("T-STALE-IDLE", stale)
		for code in ("T-STALE-FRESH", "T-STALE-DOWN", "T-STALE-OFF"):
			self.assertNotIn(code, stale, code)
		self.assertEqual(frappe.db.get_value("Machine", "T-STALE-RUN", "status"), "Unknown")
		self.assertEqual(frappe.db.get_value("Machine", "T-STALE-FRESH", "status"), "Running")
		# A Down machine stays Down: its downtime is real until a state says otherwise.
		self.assertEqual(frappe.db.get_value("Machine", "T-STALE-DOWN", "status"), "Down")
		self.assertEqual(frappe.db.get_value("Machine", "T-STALE-OFF", "status"), "Running")

	def test_threshold_comes_from_settings(self):
		from foames.foames_mes.tasks import mark_stale_machines_unknown

		frappe.db.set_single_value("Machine Data Settings", "stale_after_minutes", 120)
		self.seen("T-STALE-60", 60, "Running")
		self.assertNotIn("T-STALE-60", mark_stale_machines_unknown())
		frappe.db.set_single_value("Machine Data Settings", "stale_after_minutes", 30)
		self.assertIn("T-STALE-60", mark_stale_machines_unknown())

	def test_machine_that_never_reported_is_left_alone(self):
		from foames.foames_mes.tasks import mark_stale_machines_unknown

		machine = make_machine("T-STALE-NEVER")
		machine.db_set("status", "Running", update_modified=False)
		self.assertNotIn("T-STALE-NEVER", mark_stale_machines_unknown())


class TestMachineDefaults(IntegrationTestCase):
	def test_shift_start_stays_empty_unless_set(self):
		# Frappe fills an empty Time field with the current time on insert. An empty shift start
		# means the whole day is scheduled, so the daily OEE window would silently start "now".
		make_machine("T-DEF-NOSHIFT")
		self.assertIsNone(frappe.db.get_value("Machine", "T-DEF-NOSHIFT", "shift_start"))
		make_machine("T-DEF-SHIFT", shift_start="06:00:00")
		self.assertTrue(frappe.db.get_value("Machine", "T-DEF-SHIFT", "shift_start"))
