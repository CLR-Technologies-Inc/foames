# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Building management on a site: the register, readings through the engine, alarms from raise to
close and their suggestions, communication loss, the hourly check, utility consumption per good
unit, maintenance plans on facility assets, the topology report and the read API."""

import json

import frappe
from frappe.utils import add_to_date, now_datetime

from foames.foames_bms import api
from foames.foames_bms.doctype.building_alarm.building_alarm import acknowledge
from foames.foames_bms.engine import check_bms, check_stale_points, record_readings
from foames.foames_bms.report.utility_consumption.utility_consumption import execute as consumption_report
from foames.foames_mes.api import record_events
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user

FACILITIES = "bms-facilities@example.com"


def stamp(dt):
	return dt.strftime("%Y-%m-%dT%H:%M:%S")


def make_zone(name, parent=None, **overrides):
	if frappe.db.exists("Facility Zone", name):
		return frappe.get_doc("Facility Zone", name)
	values = {
		"doctype": "Facility Zone",
		"zone_name": name,
		"zone_type": "Area",
		"parent_facility_zone": parent,
		"is_group": 0,
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_asset(name, system="Chiller", zone=None, **overrides):
	values = {"doctype": "Facility Asset", "asset_name": name, "system": system, "zone": zone}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_point(point_id, asset, limits=None, **overrides):
	values = {
		"doctype": "Building Point",
		"point_id": point_id,
		"facility_asset": asset,
		"point_type": "Sensor",
		"quantity": "Temperature",
		"unit": "degC",
		"limits": limits or [],
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def reading(point, value, minutes_ago=0, **extra):
	return {
		"point": point,
		"value": value,
		"timestamp": stamp(add_to_date(now_datetime(), minutes=-minutes_ago)),
		**extra,
	}


def suggestions_for(alarm):
	return frappe.get_all(
		"Agent Suggestion",
		filters={"reference_doctype": "Building Alarm", "reference_name": alarm},
		fields=["name", "status", "category", "severity", "rule_key"],
		order_by="creation",
	)


class TestBuildingManagement(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.site = make_zone("T-BMS Site", zone_type="Site", is_group=1)
		self.hall = make_zone("T-BMS Hall", self.site.name, line="T-BMS-LINE")
		self.asset = make_asset("T-CH-1", zone=self.site.name, serves_zone=self.hall.name)
		self.point = make_point(
			"T-CH-1.CHWS",
			self.asset.name,
			limits=[
				{"limit_type": "High", "value": 9, "priority": "Medium"},
				{"limit_type": "High High", "value": 12, "priority": "Critical"},
			],
			deadband=0.5,
		)

	def test_register_defaults(self):
		self.assertEqual(self.asset.equipment_class, "Chiller")
		self.assertEqual(self.asset.haystack_tags, "equip chiller")
		self.assertEqual(self.point.brick_class, "Temperature_Sensor")
		self.assertEqual(self.point.alarm_condition, "Normal")
		with self.assertRaises(frappe.ValidationError):
			make_point(
				"T-BAD",
				self.asset.name,
				limits=[{"limit_type": "High", "value": 5}, {"limit_type": "Low", "value": 8}],
			)
		with self.assertRaises(frappe.ValidationError):
			make_point("T-METER-NO-UTILITY", self.asset.name, point_type="Meter")

	def test_alarm_lifecycle(self):
		result = record_readings([reading(self.point.name, 6.5, 10)])
		self.assertEqual(len(result["accepted"]), 1)
		self.assertEqual(frappe.db.get_value("Facility Asset", self.asset.name, "status"), "Normal")

		record_readings([reading(self.point.name, 10.0, 8)])
		point = frappe.get_doc("Building Point", self.point.name)
		self.assertEqual(point.alarm_condition, "High")
		alarm = frappe.get_doc("Building Alarm", point.open_alarm)
		self.assertEqual((alarm.status, alarm.priority, alarm.limit_value), ("Active", "Medium", 9))
		self.assertEqual(alarm.zone, self.site.name)
		self.assertEqual(frappe.db.get_value("Facility Asset", self.asset.name, "status"), "Alarm")
		first = suggestions_for(alarm.name)
		self.assertEqual(
			[(s.category, s.severity, s.status) for s in first], [("Facility", "Warning", "Open")]
		)

		record_readings([reading(self.point.name, 12.5, 6)])
		alarm.reload()
		self.assertEqual(
			(alarm.alarm_condition, alarm.priority, alarm.worst_value), ("High High", "Critical", 12.5)
		)
		self.assertEqual(len(suggestions_for(alarm.name)), 2)

		make_user(FACILITIES, "FoaMES Maintenance")
		with as_user(FACILITIES):
			acknowledge(alarm.name, "On my way")
		alarm.reload()
		self.assertEqual((alarm.status, alarm.acknowledged_by), ("Acknowledged", FACILITIES))
		self.assertEqual({s.status for s in suggestions_for(alarm.name)}, {"Accepted"})

		# Back under High High but within its deadband: still High High, still acknowledged.
		record_readings([reading(self.point.name, 11.8, 4)])
		self.assertEqual(
			frappe.db.get_value("Building Point", self.point.name, "alarm_condition"), "High High"
		)
		alarm.reload()
		self.assertEqual(alarm.status, "Acknowledged")
		record_readings([reading(self.point.name, 7.0, 2)])
		alarm.reload()
		self.assertEqual(alarm.status, "Closed")
		self.assertFalse(frappe.db.get_value("Building Point", self.point.name, "open_alarm"))
		self.assertEqual({s.status for s in suggestions_for(alarm.name)}, {"Done"})
		self.assertEqual(frappe.db.get_value("Facility Asset", self.asset.name, "status"), "Normal")

	def test_return_before_acknowledgement_waits_for_it(self):
		record_readings([reading(self.point.name, 10, 5), reading(self.point.name, 6, 3)])
		alarm = frappe.get_last_doc("Building Alarm", filters={"point": self.point.name})
		self.assertEqual(alarm.status, "Returned")
		alarm.acknowledge()
		self.assertEqual(alarm.status, "Closed")

	def test_rejections_and_old_readings(self):
		result = record_readings(
			[
				reading(self.point.name, 6, 5, id="r-1"),
				reading(self.point.name, 6, 5, id="r-1"),
				reading("T-NOBODY", 1),
				{"point": self.point.name, "value": "warm"},
			]
		)
		self.assertEqual(len(result["accepted"]), 1)
		self.assertEqual(
			[r["reason"] for r in result["rejected"]][:2],
			["duplicate reading id", "no enabled Building Point has id 'T-NOBODY'"],
		)
		record_readings([reading(self.point.name, 15, 30)])  # older than the present value
		self.assertEqual(frappe.db.get_value("Building Point", self.point.name, "last_value"), 6)
		self.assertEqual(frappe.db.get_value("Building Point", self.point.name, "alarm_condition"), "Normal")

	def test_bad_quality_is_not_compared(self):
		record_readings([reading(self.point.name, 50, 1, quality="Bad")])
		point = frappe.get_doc("Building Point", self.point.name)
		self.assertEqual((point.alarm_condition, point.last_quality), ("Normal", "Bad"))

	def test_communication_loss(self):
		record_readings([reading(self.point.name, 6, 90)])
		self.assertEqual(check_stale_points(), [self.point.name])
		point = frappe.get_doc("Building Point", self.point.name)
		self.assertEqual(point.alarm_condition, "Stale")
		alarm = frappe.get_doc("Building Alarm", point.open_alarm)
		self.assertEqual(alarm.alarm_condition, "Stale")
		self.assertEqual(frappe.db.get_value("Facility Asset", self.asset.name, "status"), "Stale")
		self.assertEqual(check_stale_points(), [])
		record_readings([reading(self.point.name, 6, 0)])
		alarm.reload()
		self.assertEqual(alarm.status, "Returned")

	def test_out_of_service_raises_no_suggestion(self):
		self.asset.out_of_service = 1
		self.asset.save()
		record_readings([reading(self.point.name, 13, 1)])
		alarm = frappe.get_last_doc("Building Alarm", filters={"point": self.point.name})
		self.assertEqual(suggestions_for(alarm.name), [])
		self.assertEqual(frappe.db.get_value("Facility Asset", self.asset.name, "status"), "Out of Service")

	def test_hourly_check(self):
		record_readings([reading(self.point.name, 13, 60)])
		store = make_asset("T-HAZ-1", system="Hazardous Material Storage", zone=self.site.name)
		created = check_bms()
		keys = set(frappe.get_all("Agent Suggestion", filters={"name": ("in", created)}, pluck="rule_key"))
		alarm = frappe.get_last_doc("Building Alarm", filters={"point": self.point.name})
		self.assertIn(f"bms-unacknowledged:{alarm.name}", keys)
		self.assertIn(f"bms-hazmat-no-assessment:{store.name}", keys)
		self.assertIn(f"bms-hazmat-unmonitored:{store.name}", keys)

	def test_utility_consumption_per_good_unit(self):
		meter = make_point(
			"T-HALL.KWH",
			self.asset.name,
			point_type="Meter",
			quantity="Energy",
			unit="kWh",
			utility="Electricity",
			meter_mode="Totalizer",
		)
		record_readings(
			[reading(meter.name, 1000, 120), reading(meter.name, 1060, 60), reading(meter.name, 1100, 1)]
		)
		make_machine("T-BMS-M1", line="T-BMS-LINE")
		record_events(
			[
				{
					"machine": "T-BMS-M1",
					"type": "Count",
					"value": 100,
					"timestamp": stamp(add_to_date(now_datetime(), minutes=-100)),
				},
				{
					"machine": "T-BMS-M1",
					"type": "Count",
					"value": 300,
					"timestamp": stamp(add_to_date(now_datetime(), minutes=-50)),
				},
			]
		)
		_columns, rows, _msg, _chart, summary = consumption_report(
			{"utility": "Electricity", "zone": self.site.name}
		)
		rows = [r for r in rows if r["point"] == meter.name]
		self.assertAlmostEqual(sum(r["consumption"] for r in rows), 100.0)
		self.assertEqual({r["zone"] for r in rows}, {self.hall.name})
		if len(rows) == 1:  # the readings fell on one day
			self.assertEqual(rows[0]["good_units"], 200.0)
			self.assertAlmostEqual(rows[0]["per_unit"], 0.5)
		self.assertTrue(summary)

	def test_maintenance_plan_on_a_facility_asset(self):
		status = make_point(
			"T-CH-1.RUN",
			self.asset.name,
			point_type="Status",
			value_kind="Binary",
			quantity="Run Status",
			unit="",
		)
		record_readings(
			[reading(status.name, 1, 90), reading(status.name, 1, 60), reading(status.name, 0, 30)]
		)
		plan = frappe.get_doc(
			{
				"doctype": "Maintenance Plan",
				"title": "Chiller condenser tube cleaning",
				"facility_asset": self.asset.name,
				"trigger_type": "Run Hours",
				"interval": 2,
				"last_done_on": add_to_date(now_datetime(), hours=-3),
			}
		).insert()
		self.assertAlmostEqual(plan.used, 1.0, places=1)
		work_order = frappe.get_doc(
			{"doctype": "Maintenance Work Order", "maintenance_plan": plan.name}
		).insert()
		self.assertEqual((work_order.facility_asset, work_order.machine), (self.asset.name, None))
		work_order.status = "Completed"
		work_order.save()
		self.assertFalse(work_order.downtime_record)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Maintenance Plan",
					"title": "Neither",
					"trigger_type": "Calendar",
					"interval": 30,
				}
			).insert()

	def test_topology_report(self):
		from foames.foames_bms.topology import report
		from foames.foames_topology.ingest import normalize_report

		result = normalize_report(report(), {})
		self.assertEqual(result["rejected"], [])
		ids = {a["asset_id"] for a in result["assets"]}
		self.assertTrue({"bms-zone:T-BMS Hall", "bms-asset:T-CH-1", "bms-point:T-CH-1.CHWS"} <= ids)
		self.assertIn(
			"bms-point:T-CH-1.CHWS|Read|bms-asset:T-CH-1", {b["binding_key"] for b in result["bindings"]}
		)

	def test_read_api_and_snapshot(self):
		record_readings([reading(self.point.name, 13, 1)])
		assets = api.list_facility_assets(zone=self.site.name)
		self.assertIn(self.asset.name, [a.name for a in assets])
		detail = api.get_facility_asset(self.asset.name)
		self.assertEqual(detail["points"][0]["alarm_condition"], "High High")
		self.assertEqual(len(api.list_building_alarms(facility_asset=self.asset.name)), 1)
		history = api.get_point_history(self.point.name)
		self.assertEqual([r.value for r in history["readings"]], [13])
		summary = api.get_facility_summary()
		self.assertGreaterEqual(summary["systems"]["Chiller"]["alarm"], 1)
		snapshot = {}
		from foames.foames_bms.floor import extend_snapshot

		extend_snapshot(snapshot, None, now_datetime())
		self.assertIn("facility", snapshot)
		json.dumps(snapshot, default=str)

	def test_mcp_tools_registered(self):
		from foames.foames_mcp.api import catalogue

		names = {tool.name for tool in catalogue()}
		self.assertTrue(
			{"foames_bms_list_assets", "foames_bms_list_alarms", "foames_bms_utility_consumption"} <= names
		)
		self.assertTrue(all(t.read_only for t in catalogue() if t.name.startswith("foames_bms_")))
