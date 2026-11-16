# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Building management pure logic: readings, limits with deadband and on-delay, the alarm state
step, staleness, asset status, consumption from totalizers and rate meters, run hours, and the
findings. No site needed."""

import unittest
from datetime import date, datetime, timedelta

from foames.foames_bms import bms

T0 = datetime(2026, 11, 16, 8, 0, 0)


def at(minutes=0, seconds=0):
	return T0 + timedelta(minutes=minutes, seconds=seconds)


HIGH = {"limit_type": "High", "value": 27.0, "priority": "Medium", "delay_seconds": 0}
HIGH_HIGH = {"limit_type": "High High", "value": 32.0, "priority": "Critical", "delay_seconds": 0}
LOW = {"limit_type": "Low", "value": 15.0, "priority": "Low", "delay_seconds": 0}


class TestReadings(unittest.TestCase):
	def test_values(self):
		self.assertEqual(bms.reading_value(21.5), 21.5)
		self.assertEqual(bms.reading_value("21.5"), 21.5)
		self.assertEqual(bms.reading_value(True), 1.0)
		self.assertEqual(bms.reading_value("active"), 1.0)
		self.assertEqual(bms.reading_value("OFF"), 0.0)
		for bad in ("warm", None, float("nan"), "inf"):
			with self.assertRaises(bms.ReadingError):
				bms.reading_value(bad)

	def test_normalise(self):
		reading = bms.normalise_reading(
			{"point": " AHU-1.SAT ", "value": "13.2", "timestamp": "2026-11-16T08:00:00"}
		)
		self.assertEqual(reading["point"], "AHU-1.SAT")
		self.assertEqual(reading["timestamp"], T0)
		self.assertEqual(reading["quality"], "Good")
		self.assertTrue(reading["reading_key"].startswith("bms:"))
		again = bms.normalise_reading(
			{"point": "AHU-1.SAT", "value": 13.2, "timestamp": "2026-11-16T08:00:00"}
		)
		self.assertEqual(reading["reading_key"], again["reading_key"])
		self.assertEqual(
			bms.normalise_reading(
				{"point": "P", "value": 1, "timestamp": "2026-11-16T08:00:00", "id": "x-1"}
			)["reading_key"],
			"x-1",
		)
		with self.assertRaises(bms.ReadingError):
			bms.normalise_reading({"value": 1})
		with self.assertRaises(bms.ReadingError):
			bms.normalise_reading({"point": "P"})
		with self.assertRaises(bms.ReadingError):
			bms.normalise_reading({"point": "P", "value": 1, "quality": "great"})
		with self.assertRaises(bms.ReadingError):
			bms.normalise_reading({"point": "P", "value": 1, "timestamp": "yesterday"})


class TestLimits(unittest.TestCase):
	def test_check_limits(self):
		self.assertEqual(bms.check_limits([HIGH, HIGH_HIGH, LOW]), [])
		self.assertIn("High High is below High", bms.check_limits([HIGH, {**HIGH_HIGH, "value": 20}]))
		self.assertIn("High is set twice", bms.check_limits([HIGH, HIGH]))
		self.assertTrue(bms.check_limits([{**HIGH, "value": 10}, LOW]))
		self.assertTrue(bms.check_limits([{"limit_type": "Sideways", "value": 1}]))

	def test_most_severe_limit_wins(self):
		self.assertEqual(bms.evaluate(33, [HIGH, HIGH_HIGH, LOW])["limit_type"], "High High")
		self.assertEqual(bms.evaluate(28, [HIGH, HIGH_HIGH, LOW])["limit_type"], "High")
		self.assertEqual(bms.evaluate(10, [HIGH, HIGH_HIGH, LOW])["limit_type"], "Low")
		self.assertIsNone(bms.evaluate(21, [HIGH, HIGH_HIGH, LOW]))
		self.assertIsNone(bms.evaluate(27, [HIGH]))  # at the limit is not past it

	def test_deadband_holds_an_active_condition(self):
		self.assertEqual(bms.evaluate(26.5, [HIGH], current="High", deadband=1)["limit_type"], "High")
		self.assertIsNone(bms.evaluate(25.9, [HIGH], current="High", deadband=1))
		self.assertIsNone(bms.evaluate(26.5, [HIGH], current=None, deadband=1))
		self.assertEqual(bms.evaluate(15.5, [LOW], current="Low", deadband=1)["limit_type"], "Low")

	def test_alarm_state(self):
		leak = [{"limit_type": "Alarm State", "value": 1, "priority": "High"}]
		self.assertEqual(bms.evaluate(1, leak)["priority"], "High")
		self.assertIsNone(bms.evaluate(0, leak))


class TestStep(unittest.TestCase):
	def test_raise_update_change_return(self):
		state = {"condition": "Normal"}
		state, action, limit = bms.step(state, 28, at(0), [HIGH, HIGH_HIGH])
		self.assertEqual((state["condition"], action, limit["limit_type"]), ("High", "raise", "High"))
		state, action, _ = bms.step(state, 29, at(1), [HIGH, HIGH_HIGH])
		self.assertEqual((state["condition"], action), ("High", "update"))
		state, action, limit = bms.step(state, 33, at(2), [HIGH, HIGH_HIGH])
		self.assertEqual((state["condition"], action, limit["priority"]), ("High High", "change", "Critical"))
		state, action, _ = bms.step(state, 20, at(3), [HIGH, HIGH_HIGH])
		self.assertEqual((state["condition"], action), ("Normal", "return"))
		_state, action, _ = bms.step(state, 21, at(4), [HIGH, HIGH_HIGH])
		self.assertIsNone(action)

	def test_on_delay(self):
		delayed = [{**HIGH, "delay_seconds": 300}]
		state, action, _ = bms.step({"condition": "Normal"}, 28, at(0), delayed)
		self.assertEqual((state["condition"], state["pending_condition"], action), ("Normal", "High", None))
		state, action, _ = bms.step(state, 28, at(4), delayed)
		self.assertIsNone(action)
		self.assertEqual(state["pending_since"], at(0))
		state, action, _ = bms.step(state, 28, at(5), delayed)
		self.assertEqual((state["condition"], action), ("High", "raise"))

	def test_a_dip_resets_the_on_delay(self):
		delayed = [{**HIGH, "delay_seconds": 300}]
		state, _a, _l = bms.step({"condition": "Normal"}, 28, at(0), delayed)
		state, _a, _l = bms.step(state, 20, at(2), delayed)
		self.assertIsNone(state["pending_condition"])
		state, action, _ = bms.step(state, 28, at(5), delayed)
		self.assertIsNone(action)
		self.assertEqual(state["pending_since"], at(5))

	def test_a_reading_after_stale_returns_or_changes(self):
		_state, action, _ = bms.step({"condition": "Stale"}, 21, at(0), [HIGH])
		self.assertEqual(action, "return")
		state, action, _ = bms.step({"condition": "Stale"}, 28, at(0), [HIGH])
		self.assertEqual((state["condition"], action), ("High", "change"))

	def test_worse(self):
		self.assertEqual(bms.worse("High", 30, 29), 30)
		self.assertEqual(bms.worse("Low", 10, 9), 9)
		self.assertEqual(bms.worse("High", None, 29), 29)


class TestStaleAndStatus(unittest.TestCase):
	def test_stale(self):
		self.assertFalse(bms.is_stale(None, at(500), 0))
		self.assertFalse(bms.is_stale(at(0), at(60), 0))
		self.assertTrue(bms.is_stale(at(0), at(61), 0))
		self.assertTrue(bms.is_stale(at(0), at(11), 10))

	def test_asset_status(self):
		self.assertEqual(bms.asset_status([], False), "Unknown")
		self.assertEqual(bms.asset_status([{"condition": "Normal", "last_value_at": T0}]), "Normal")
		self.assertEqual(
			bms.asset_status(
				[{"condition": "Normal", "last_value_at": T0}, {"condition": "Stale", "last_value_at": T0}]
			),
			"Stale",
		)
		self.assertEqual(
			bms.asset_status(
				[{"condition": "High", "last_value_at": T0}, {"condition": "Stale", "last_value_at": T0}]
			),
			"Alarm",
		)
		self.assertEqual(
			bms.asset_status([{"condition": "High", "last_value_at": T0, "disabled": 1}]), "Unknown"
		)
		self.assertEqual(bms.asset_status([{"condition": "High"}], out_of_service=True), "Out of Service")


class TestConsumption(unittest.TestCase):
	def test_totalizer(self):
		readings = [(at(0), 1000.0), (at(15), 1010.0), (at(30), 1025.0)]
		self.assertEqual(bms.totalizer_consumption(readings), 25.0)

	def test_totalizer_reset_counts_nothing_and_rollover_counts(self):
		self.assertEqual(bms.totalizer_consumption([(at(0), 990.0), (at(1), 5.0), (at(2), 8.0)]), 3.0)
		self.assertEqual(bms.totalizer_consumption([(at(0), 990.0), (at(1), 5.0)], rollover=1000), 15.0)

	def test_rate_trapezoid_and_gaps(self):
		readings = [(at(0), 100.0), (at(30), 200.0), (at(60), 200.0)]
		self.assertAlmostEqual(bms.rate_consumption(readings), 75.0 + 100.0)
		gappy = [(at(0), 100.0), (at(180), 100.0)]
		self.assertEqual(bms.rate_consumption(gappy, max_gap_minutes=60), 0.0)
		per_minute = [(at(0), 10.0), (at(1), 10.0)]
		self.assertAlmostEqual(bms.rate_consumption(per_minute, per_hours=1 / 60), 10.0)
		self.assertEqual(bms.rate_consumption([(at(0), -5.0), (at(30), -5.0)]), 0.0)

	def test_by_period_charges_the_later_reading(self):
		readings = [
			(datetime(2026, 11, 15, 23, 50), 100.0),
			(datetime(2026, 11, 16, 0, 10), 110.0),
			(datetime(2026, 11, 16, 12, 0), 150.0),
		]
		self.assertEqual(bms.consumption_by_period("Totalizer", readings, "Day"), {date(2026, 11, 16): 50.0})
		with self.assertRaises(ValueError):
			bms.consumption("Odometer", readings)

	def test_period_start(self):
		self.assertEqual(bms.period_start(datetime(2026, 11, 19, 5), "Week"), date(2026, 11, 16))
		self.assertEqual(bms.period_start(date(2026, 11, 19), "Month"), date(2026, 11, 1))

	def test_intensity(self):
		self.assertEqual(bms.intensity(500.0, 1000.0), 0.5)
		self.assertIsNone(bms.intensity(500.0, 0))


class TestRunHours(unittest.TestCase):
	def test_holds_between_readings_up_to_the_gap(self):
		readings = [(at(0), 1.0), (at(30), 1.0), (at(60), 0.0), (at(90), 1.0)]
		self.assertAlmostEqual(bms.run_hours(readings, at(0), at(120)), 1.5)

	def test_silence_stops_the_meter(self):
		self.assertAlmostEqual(bms.run_hours([(at(0), 1.0)], at(0), at(600), max_gap_minutes=60), 1.0)

	def test_reading_before_the_window_counts_from_since(self):
		self.assertAlmostEqual(bms.run_hours([(at(-30), 1.0), (at(30), 0.0)], at(0), at(60)), 0.5)
		self.assertEqual(bms.run_hours([(at(0), 1.0)], at(10), at(5)), 0.0)


class TestTags(unittest.TestCase):
	def test_defaults(self):
		self.assertEqual(bms.default_equipment_class("Chiller"), "Chiller")
		self.assertIsNone(bms.default_equipment_class("Server Room"))
		self.assertEqual(bms.default_equipment_tags("Rooftop Unit"), "equip ahu rtu")
		self.assertEqual(bms.default_equipment_tags("Server Room"), "equip")
		self.assertEqual(bms.default_point_class("Sensor", "Temperature"), "Temperature_Sensor")
		self.assertEqual(bms.default_point_tags("Meter", "Energy", "Electricity"), "point energy meter elec")
		self.assertEqual(bms.tag_set("point, sensor  temp"), {"point", "sensor", "temp"})


class TestFindings(unittest.TestCase):
	def alarm(self, **overrides):
		values = {
			"name": "BAL-2026-00001",
			"point": "SRV-1.TEMP",
			"point_title": "Server room temperature",
			"facility_asset": "SRV-1",
			"system": "Server Room",
			"zone": "IT Room",
			"condition": "High",
			"priority": "High",
			"value": 29.0,
			"limit": 27.0,
			"unit": "degC",
			"raised_at": T0,
		}
		values.update(overrides)
		return values

	def test_alarm_finding(self):
		finding = bms.alarm_finding(self.alarm())
		self.assertEqual(finding["rule_key"], "bms-alarm:BAL-2026-00001:High")
		self.assertEqual((finding["category"], finding["severity"]), ("Facility", "Critical"))
		self.assertIn("29.0 degC", finding["suggestion"])
		self.assertEqual(finding["reference_doctype"], "Building Alarm")

	def test_hazmat_alarm_is_a_safety_finding(self):
		finding = bms.alarm_finding(
			self.alarm(
				system="Hazardous Material Storage", condition="Alarm State", hazard_assessment="HAZ-0001"
			)
		)
		self.assertEqual((finding["category"], finding["severity"]), ("Safety", "Critical"))
		self.assertIn("HAZ-0001", finding["suggestion"])

	def test_stale_finding(self):
		finding = bms.alarm_finding(self.alarm(condition="Stale", priority="Medium", last_value_at=T0))
		self.assertEqual(finding["severity"], "Warning")
		self.assertIn("stopped reporting", finding["suggestion"])

	def test_unacknowledged(self):
		rows = [
			{**self.alarm(), "status": "Active", "raised_at": at(-45)},
			{**self.alarm(name="B2"), "status": "Active", "raised_at": at(-10)},
			{**self.alarm(name="B3", priority="Low"), "status": "Active", "raised_at": at(-45)},
			{**self.alarm(name="B4"), "status": "Acknowledged", "raised_at": at(-45)},
		]
		findings = bms.unacknowledged_findings(rows, at(0))
		self.assertEqual([f["reference_name"] for f in findings], ["BAL-2026-00001"])

	def test_hazmat_register_findings(self):
		findings = bms.hazmat_findings(
			[
				{
					"name": "HAZ-ST-1",
					"system": "Hazardous Material Storage",
					"hazard_assessment_active": False,
					"point_count": 0,
				},
				{
					"name": "HAZ-ST-2",
					"system": "Hazardous Material Storage",
					"hazard_assessment_active": True,
					"point_count": 2,
				},
				{"name": "HAZ-ST-3", "system": "Hazardous Material Storage", "out_of_service": 1},
				{"name": "CH-1", "system": "Chiller"},
			]
		)
		self.assertEqual(
			sorted(f["rule_key"] for f in findings),
			["bms-hazmat-no-assessment:HAZ-ST-1", "bms-hazmat-unmonitored:HAZ-ST-1"],
		)


if __name__ == "__main__":
	unittest.main()
