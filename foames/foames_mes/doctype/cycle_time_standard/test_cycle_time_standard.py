# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Cycle Time Standard on a site: validation, the stored one-cycle figures, one default per machine,
and the projection API with scenarios, observed time and batches for a scheduler."""

import frappe

from foames.foames_mes.api import record_events
from foames.foames_mes.cycle_time_api import (
	compare_with_observed,
	get_observed_cycle,
	project_operations,
	project_time,
)
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import make_machine

DAY = "2026-10-20"
ELEMENTS = [
	{"element_name": "Load", "kind": "Manual", "seconds": 20},
	{"element_name": "Cut", "kind": "Automatic", "seconds": 90},
	{"element_name": "Unload", "kind": "Manual", "seconds": 10},
	{"element_name": "Deburr", "kind": "Manual", "seconds": 25, "internal": 1},
	{"element_name": "Setup", "kind": "Manual", "seconds": 1800, "per": "Batch"},
]


def make_standard(machine="T-CT", **overrides):
	values = {
		"doctype": "Cycle Time Standard",
		"title": "Turn shaft OP20",
		"machine": machine,
		"parts_per_cycle": 1,
		"allowance_percent": 10,
		"elements": [dict(row) for row in ELEMENTS],
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


class TestCycleTimeStandard(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-CT")
		make_machine("T-CT-OBS")

	def test_one_cycle_is_stored(self):
		doc = make_standard()
		self.assertAlmostEqual(doc.automatic_seconds, 90.0)
		self.assertAlmostEqual(doc.manual_external_seconds, 33.0)
		self.assertAlmostEqual(doc.manual_internal_seconds, 27.5)
		self.assertAlmostEqual(doc.cycle_seconds, 123.0)
		self.assertAlmostEqual(doc.manual_seconds, 60.5)
		self.assertAlmostEqual(doc.setup_seconds, 1980.0)
		self.assertAlmostEqual(doc.automation_percent, 90.0 / 123.0 * 100.0, places=4)

	def test_invalid_standards_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_standard(parts_per_cycle=0)
		with self.assertRaises(frappe.ValidationError):
			make_standard(
				elements=[{"element_name": "Setup", "kind": "Manual", "seconds": 60, "per": "Batch"}]
			)
		with self.assertRaises(frappe.ValidationError):
			make_standard(machine=None, is_default=1)

	def test_one_default_per_machine(self):
		first = make_standard(is_default=1)
		second = make_standard(is_default=1)
		self.assertEqual(frappe.db.get_value("Cycle Time Standard", first.name, "is_default"), 0)
		self.assertEqual(project_time(machine="T-CT", quantity=10)["standard"], second.name)

	def test_project_time(self):
		doc = make_standard(labor_rate=30, machine_rate=60)
		p = project_time(standard=doc.name, quantity=100)
		self.assertEqual(p["cycles"], 100)
		self.assertAlmostEqual(p["elapsed_minutes"], (1980 + 12300) / 60)
		self.assertAlmostEqual(p["operator_minutes"], (1980 + 6050) / 60)
		self.assertAlmostEqual(p["automatic_minutes"], 9000 / 60)
		self.assertEqual(p["machine"], "T-CT")

	def test_scenario(self):
		doc = make_standard(labor_rate=30)
		result = project_time(
			standard=doc.name,
			quantity=100,
			changes=frappe.as_json(
				[
					{"element": "Load", "kind": "Automatic", "seconds": 8},
					{"element": "Unload", "kind": "Automatic", "seconds": 6},
				]
			),
			annual_quantity=10000,
		)
		self.assertAlmostEqual(result["baseline"]["cycle"]["cycle_seconds"], 123.0)
		self.assertAlmostEqual(result["scenario"]["cycle"]["cycle_seconds"], 104.0)
		self.assertAlmostEqual(result["annual"]["operator_hours_saved"], 33.0 * 10000 / 3600)
		# The saved standard is untouched.
		self.assertAlmostEqual(frappe.db.get_value("Cycle Time Standard", doc.name, "cycle_seconds"), 123.0)

	def test_invalid_scenario_is_refused(self):
		doc = make_standard()
		with self.assertRaises(frappe.ValidationError):
			project_time(standard=doc.name, quantity=1, changes=[{"element": "Cut", "seconds": -1}])

	def test_observed_and_calibrated(self):
		record_events(
			[
				{"machine": "T-CT-OBS", "type": "State", "state": "Running", "timestamp": f"{DAY}T08:00:00"},
				{"machine": "T-CT-OBS", "type": "State", "state": "Idle", "timestamp": f"{DAY}T10:00:00"},
				{"machine": "T-CT-OBS", "type": "State", "state": "Running", "timestamp": f"{DAY}T10:30:00"},
				{"machine": "T-CT-OBS", "type": "State", "state": "Idle", "timestamp": f"{DAY}T12:00:00"},
				{"machine": "T-CT-OBS", "type": "Count", "value": 0, "timestamp": f"{DAY}T07:59:00"},
				{"machine": "T-CT-OBS", "type": "Count", "value": 140, "timestamp": f"{DAY}T12:00:00"},
			]
		)
		since, until = f"{DAY} 08:00:00", f"{DAY} 13:00:00"
		obs = get_observed_cycle("T-CT-OBS", since=since, until=until)
		self.assertEqual(obs["parts"], 140)
		self.assertAlmostEqual(obs["automatic_seconds"], 12600 / 140)
		self.assertAlmostEqual(obs["idle_seconds_per_cycle"], 5400 / 140)

		doc = make_standard(machine="T-CT-OBS")
		cmp = compare_with_observed(standard=doc.name, since=since, until=until)
		self.assertAlmostEqual(cmp["automatic_variance_percent"], 0.0, places=6)
		self.assertAlmostEqual(cmp["cycle_variance_percent"], ((18000 / 140) - 123) / 123 * 100, places=6)

		p = project_time(standard=doc.name, quantity=10, use_observed=1, since=since, until=until)
		self.assertIn("observed", p)
		self.assertTrue(any("scaled by 1.000" in n for n in p["notes"]))

	def test_project_operations_for_a_scheduler(self):
		doc = make_standard(is_default=1)
		out = project_operations(
			frappe.as_json(
				[
					{"key": "WO-1/OP20", "standard": doc.name, "quantity": 10},
					{"key": "WO-2/OP20", "machine": "T-CT", "quantity": 20},
					{"key": "WO-3/OP10", "machine": "T-CT-NONE", "quantity": 5},
				]
			)
		)
		rows = {row["key"]: row for row in out["operations"]}
		self.assertAlmostEqual(rows["WO-1/OP20"]["elapsed_minutes"], (1980 + 1230) / 60)
		self.assertAlmostEqual(rows["WO-2/OP20"]["elapsed_minutes"], (1980 + 2460) / 60)
		self.assertIn("error", rows["WO-3/OP10"])
		self.assertAlmostEqual(out["totals"]["elapsed_minutes"], (1980 * 2 + 1230 + 2460) / 60)
