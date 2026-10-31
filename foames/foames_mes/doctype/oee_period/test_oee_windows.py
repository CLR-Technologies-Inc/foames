# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OEE Period on a site: validation, how the state history and counts enter a window, the scheduled
windows and the daily task."""

import frappe
from frappe.utils import get_datetime

from foames.foames_mes.api import record_events
from foames.foames_mes.doctype.oee_period.oee_period import compute_daily_oee, get_oee, scheduled_window
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_reason, make_user

DAY = "2026-10-20"


def period(machine="T-OW", start=f"{DAY} 08:00:00", end=f"{DAY} 09:00:00", planned=60, **overrides):
	values = {
		"doctype": "OEE Period",
		"machine": machine,
		"from_time": start,
		"to_time": end,
		"planned_minutes": planned,
	}
	values.update(overrides)
	return frappe.get_doc(values)


class TestOEEPeriodValidation(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-OW", ideal_cycle_seconds=30)

	def test_must_end_after_it_starts(self):
		with self.assertRaises(frappe.ValidationError):
			period(end=f"{DAY} 08:00:00").insert()
		with self.assertRaises(frappe.ValidationError):
			period(end=f"{DAY} 07:00:00").insert()

	def test_planned_minutes_must_be_positive(self):
		for planned in (0, -5, None):
			with self.assertRaises(frappe.ValidationError, msg=planned):
				period(planned=planned).insert()

	def test_ideal_cycle_defaults_to_the_machine(self):
		self.assertEqual(period().insert().ideal_cycle_seconds, 30)
		later = period(start=f"{DAY} 09:00:00", end=f"{DAY} 10:00:00", ideal_cycle_seconds=45)
		self.assertEqual(later.insert().ideal_cycle_seconds, 45)

	def test_period_without_any_signal_is_all_unknown(self):
		doc = period().insert()
		self.assertEqual((doc.run_minutes, doc.unknown_minutes, doc.coverage), (0, 60, 0))
		self.assertEqual((doc.availability, doc.performance, doc.quality, doc.oee), (0, 0, 0, 0))
		self.assertEqual((doc.good_count, doc.scrap_count), (0, 0))


class TestStateHistoryInAWindow(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-OW", ideal_cycle_seconds=30)
		make_reason("T-OW-PM", "Planned")

	def events(self, *specs):
		record_events(
			[
				{"machine": "T-OW", "type": "State", "state": state, "timestamp": f"{DAY} {at}"}
				for at, state in specs
			]
		)

	def test_state_before_the_window_carries_in(self):
		self.events(("07:00:00", "Running"))
		doc = period().insert()
		self.assertEqual((doc.run_minutes, doc.unknown_minutes, doc.coverage), (60, 0, 100))
		self.assertEqual(doc.availability, 100)

	def test_latest_state_before_the_window_wins(self):
		self.events(("06:00:00", "Running"), ("07:00:00", "Down"), ("07:30:00", "Idle"))
		doc = period().insert()
		self.assertEqual((doc.run_minutes, doc.unplanned_downtime_minutes), (0, 0))
		self.assertEqual(doc.unknown_minutes, 0)  # Idle is known time, just not run time

	def test_changes_inside_the_window_split_it(self):
		self.events(("08:00:00", "Running"), ("08:30:00", "Down"), ("08:45:00", "Running"))
		doc = period().insert()
		self.assertEqual((doc.run_minutes, doc.unplanned_downtime_minutes), (45, 15))
		self.assertAlmostEqual(doc.availability, 75)

	def test_downtime_with_a_planned_reason_is_planned(self):
		self.events(("08:00:00", "Running"), ("08:30:00", "Down"), ("08:45:00", "Running"))
		closed = frappe.db.get_value("Downtime Record", {"machine": "T-OW", "status": "Closed"}, "name")
		frappe.db.set_value("Downtime Record", closed, "reason", "T-OW-PM")
		doc = period().insert()
		self.assertEqual((doc.planned_downtime_minutes, doc.unplanned_downtime_minutes), (15, 0))
		# Planned downtime leaves the available time: 45 run minutes over 45 available.
		self.assertAlmostEqual(doc.availability, 100)

	def test_alarm_counts_as_down(self):
		self.events(("08:00:00", "Running"))
		record_events([{"machine": "T-OW", "type": "Alarm", "code": 7, "timestamp": f"{DAY} 08:30:00"}])
		doc = period().insert()
		self.assertEqual((doc.run_minutes, doc.unplanned_downtime_minutes), (30, 30))

	def test_downtime_closed_before_the_window_does_not_count(self):
		self.events(("06:00:00", "Running"), ("07:00:00", "Down"), ("07:30:00", "Running"))
		doc = period().insert()
		self.assertEqual((doc.run_minutes, doc.unplanned_downtime_minutes), (60, 0))

	def test_counts_only_inside_the_window(self):
		self.events(("07:00:00", "Running"))
		record_events(
			[
				{"machine": "T-OW", "type": "Count", "value": 100, "timestamp": f"{DAY} 07:00:00"},
				{"machine": "T-OW", "type": "Count", "value": 150, "timestamp": f"{DAY} 08:30:00"},
				{"machine": "T-OW", "type": "Count", "value": 180, "timestamp": f"{DAY} 09:30:00"},
				{
					"machine": "T-OW",
					"type": "Count",
					"counter": "scrap",
					"value": 1,
					"timestamp": f"{DAY} 08:00:00",
				},
				{
					"machine": "T-OW",
					"type": "Count",
					"counter": "scrap",
					"value": 3,
					"timestamp": f"{DAY} 08:50:00",
				},
			]
		)
		doc = period().insert()
		self.assertEqual((doc.good_count, doc.scrap_count), (50, 2))
		# 30 s ideal over 60 run minutes allows 120 pieces; 52 were made.
		self.assertAlmostEqual(doc.performance, 52 / 120 * 100, places=3)
		self.assertAlmostEqual(doc.quality, 50 / 52 * 100, places=3)

	def test_on_demand_oee_defaults_planned_time_to_the_window(self):
		self.events(("08:00:00", "Running"))
		result = get_oee("T-OW", f"{DAY} 08:00:00", f"{DAY} 10:00:00")
		self.assertEqual((result["run_minutes"], result["availability"], result["coverage"]), (120, 100, 100))
		self.assertEqual(frappe.db.count("OEE Period", {"machine": "T-OW"}), 0)
		self.assertIsInstance(result["notes"], list)

	def test_on_demand_oee_notes_the_gaps(self):
		result = get_oee("T-OW", f"{DAY} 08:00:00", f"{DAY} 09:00:00")
		self.assertTrue(any("without a machine signal" in note for note in result["notes"]))


class TestScheduledWindow(IntegrationTestCase):
	def test_shift_window(self):
		start, end, planned = scheduled_window(get_datetime(DAY).date(), "06:00:00", 480)
		self.assertEqual(
			(start, end, planned), (get_datetime(f"{DAY} 06:00:00"), get_datetime(f"{DAY} 14:00:00"), 480)
		)

	def test_without_a_shift_the_whole_day_is_planned(self):
		start, end, planned = scheduled_window(get_datetime(DAY).date(), None, 480)
		self.assertEqual(
			(start, end, planned),
			(get_datetime(f"{DAY} 00:00:00"), get_datetime("2026-10-21 00:00:00"), 1440),
		)

	def test_shift_without_minutes_falls_back_to_the_day(self):
		start, end, planned = scheduled_window(get_datetime(DAY).date(), "06:00:00", 0)
		self.assertEqual((end - start).total_seconds() / 60, 1440)
		self.assertEqual(planned, 1440)


class TestDailyTask(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-OW-SHIFT", shift_start="06:00:00", scheduled_minutes_per_day=600)
		make_machine("T-OW-ALLDAY", scheduled_minutes_per_day=480)
		make_machine("T-OW-OFF", disabled=1)

	def test_creates_one_period_per_enabled_machine(self):
		created = compute_daily_oee(DAY)
		for code in ("T-OW-SHIFT", "T-OW-ALLDAY"):
			self.assertEqual(frappe.db.count("OEE Period", {"machine": code}), 1, code)
		self.assertEqual(frappe.db.count("OEE Period", {"machine": "T-OW-OFF"}), 0)
		self.assertGreaterEqual(len(created), 2)

	def test_running_twice_creates_nothing_new(self):
		compute_daily_oee(DAY)
		before = frappe.db.count("OEE Period")
		self.assertEqual(compute_daily_oee(DAY), [])
		self.assertEqual(frappe.db.count("OEE Period"), before)

	def test_windows_follow_the_machine_settings(self):
		compute_daily_oee(DAY)
		shift = frappe.get_doc("OEE Period", {"machine": "T-OW-SHIFT"})
		self.assertEqual(
			(str(shift.from_time), str(shift.to_time), shift.planned_minutes),
			(f"{DAY} 06:00:00", f"{DAY} 16:00:00", 600),
		)
		allday = frappe.get_doc("OEE Period", {"machine": "T-OW-ALLDAY"})
		self.assertEqual(
			(str(allday.from_time), str(allday.to_time), allday.planned_minutes),
			(f"{DAY} 00:00:00", "2026-10-21 00:00:00", 1440),
		)


class TestOEEPermissions(IntegrationTestCase):
	def test_reading_oee_needs_read_permission_on_periods(self):
		make_machine("T-OW")
		make_user("foames-oee-nobody@example.com")
		make_user("foames-oee-quality@example.com", "FoaMES Quality")
		with as_user("foames-oee-nobody@example.com"), self.assertRaises(frappe.PermissionError):
			get_oee("T-OW", f"{DAY} 08:00:00", f"{DAY} 09:00:00")
		with as_user("foames-oee-quality@example.com"):
			self.assertIn("oee", get_oee("T-OW", f"{DAY} 08:00:00", f"{DAY} 09:00:00"))
