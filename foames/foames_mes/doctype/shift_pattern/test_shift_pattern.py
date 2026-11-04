# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Shift Pattern on a site: validation, one OEE period per shift from the daily task, non-working
days, the current shift on the floor snapshot and the MTBF operating windows."""

import frappe
from frappe.utils import get_datetime

from foames.foames_mes.doctype.oee_period.oee_period import compute_daily_oee, operating_windows
from foames.foames_mes.floor import floor_snapshot
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import make_machine

TUESDAY = "2026-10-20"
WEEKDAYS = {"monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1, "saturday": 0, "sunday": 0}
EVERY_DAY = dict.fromkeys(WEEKDAYS, 1)


def shift(name, start, minutes=480, days=WEEKDAYS):
	return {"shift_name": name, "start_time": start, "duration_minutes": minutes, **days}


def make_pattern(name, shifts, holidays=()):
	if frappe.db.exists("Shift Pattern", name):
		frappe.delete_doc("Shift Pattern", name, force=True)
	return frappe.get_doc(
		{
			"doctype": "Shift Pattern",
			"pattern_name": name,
			"shifts": shifts,
			"holidays": [{"holiday_date": d, "description": "Shutdown"} for d in holidays],
		}
	).insert()


def three_shift(holidays=()):
	return make_pattern(
		"T-3SHIFT",
		[shift("Early", "06:00:00"), shift("Late", "14:00:00"), shift("Night", "22:00:00")],
		holidays,
	)


class TestShiftPatternValidation(IntegrationTestCase):
	def test_overlapping_shifts_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_pattern("T-OVERLAP", [shift("A", "06:00:00", 600), shift("B", "14:00:00")])

	def test_shift_longer_than_a_day_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_pattern("T-LONG", [shift("A", "06:00:00", 1500)])

	def test_duplicate_non_working_day_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_pattern("T-DUP", [shift("A", "06:00:00")], [TUESDAY, TUESDAY])

	def test_valid_three_shift_pattern(self):
		self.assertEqual(len(three_shift().shifts), 3)


class TestDailyOEEWithShifts(IntegrationTestCase):
	def test_one_period_per_shift(self):
		three_shift()
		make_machine("T-SP-3", shift_pattern="T-3SHIFT")
		compute_daily_oee(TUESDAY)
		periods = frappe.get_all(
			"OEE Period",
			filters={"machine": "T-SP-3"},
			fields=["shift", "from_time", "to_time", "planned_minutes"],
			order_by="from_time asc",
		)
		self.assertEqual([p.shift for p in periods], ["Early", "Late", "Night"])
		self.assertEqual([p.planned_minutes for p in periods], [480, 480, 480])
		self.assertEqual(get_datetime(periods[2].from_time), get_datetime(f"{TUESDAY} 22:00:00"))
		self.assertEqual(get_datetime(periods[2].to_time), get_datetime("2026-10-21 06:00:00"))
		self.assertEqual(compute_daily_oee(TUESDAY), [])

	def test_no_period_on_a_non_working_day_or_weekend(self):
		three_shift(holidays=[TUESDAY])
		make_machine("T-SP-HOL", shift_pattern="T-3SHIFT")
		compute_daily_oee(TUESDAY)
		compute_daily_oee("2026-10-24")  # a Saturday
		self.assertEqual(frappe.db.count("OEE Period", {"machine": "T-SP-HOL"}), 0)

	def test_pattern_overrides_shift_start(self):
		three_shift()
		make_machine(
			"T-SP-OVR", shift_pattern="T-3SHIFT", shift_start="07:00:00", scheduled_minutes_per_day=600
		)
		compute_daily_oee(TUESDAY)
		self.assertEqual(frappe.db.count("OEE Period", {"machine": "T-SP-OVR"}), 3)
		self.assertFalse(frappe.db.exists("OEE Period", {"machine": "T-SP-OVR", "shift": ("is", "not set")}))


class TestShiftOnTheFloor(IntegrationTestCase):
	def test_snapshot_names_the_running_shift(self):
		make_pattern("T-ROUND", [shift("Round The Clock", "00:00:00", 1440, EVERY_DAY)])
		make_machine("T-SP-FLOOR", shift_pattern="T-ROUND")
		make_machine("T-SP-NOPAT")
		machines = {m["name"]: m for m in floor_snapshot(days=1)["machines"]}
		self.assertEqual(machines["T-SP-FLOOR"]["shift"]["name"], "Round The Clock")
		self.assertIsNone(machines["T-SP-NOPAT"]["shift"])


class TestOperatingWindows(IntegrationTestCase):
	def test_windows_include_the_night_shift_from_the_day_before(self):
		three_shift()
		machine = frappe._dict(shift_pattern="T-3SHIFT")
		windows = operating_windows(
			machine, get_datetime("2026-10-21 00:00:00"), get_datetime("2026-10-21 12:00:00")
		)
		self.assertEqual(
			windows,
			[
				(get_datetime("2026-10-21 00:00:00"), get_datetime("2026-10-21 06:00:00")),
				(get_datetime("2026-10-21 06:00:00"), get_datetime("2026-10-21 12:00:00")),
			],
		)

	def test_machine_without_pattern_keeps_its_single_window(self):
		machine = frappe._dict(shift_start="06:00:00", scheduled_minutes_per_day=480)
		windows = operating_windows(
			machine, get_datetime(f"{TUESDAY} 00:00:00"), get_datetime("2026-10-21 00:00:00")
		)
		self.assertEqual(
			windows, [(get_datetime(f"{TUESDAY} 06:00:00"), get_datetime(f"{TUESDAY} 14:00:00"))]
		)


class TestOEETrendByShift(IntegrationTestCase):
	def test_group_and_filter_by_shift(self):
		from foames.foames_mes.report.oee_trend.oee_trend import execute

		three_shift()
		make_machine("T-SP-TREND", shift_pattern="T-3SHIFT", line="T-SP-LINE")
		compute_daily_oee(TUESDAY)
		filters = {"from_date": TUESDAY, "to_date": TUESDAY, "line": "T-SP-LINE"}
		_columns, rows, *_ = execute({**filters, "group_by": "Shift"})
		self.assertEqual(sorted(r["group"] for r in rows), ["Early", "Late", "Night"])
		_columns, rows, *_ = execute({**filters, "group_by": "Machine", "shift": "Night"})
		self.assertEqual([(r["machine"], r["periods"]) for r in rows], [("T-SP-TREND", 1)])
