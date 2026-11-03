# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""SPC over Measurement events on a Frappe site: settings, suggestions, the control chart report and
the JSON endpoint."""

import frappe
from frappe.desk.query_report import run as run_report
from frappe.utils import add_to_date, get_datetime

from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
from foames.foames_mes.floor import collect_findings
from foames.foames_mes.spc_monitor import (
	get_control_chart,
	measured_pairs,
	measurement_series,
	spc_findings,
	spc_settings,
)
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import make_machine

MACHINE = "T-SPC-1"
NOW = get_datetime("2026-11-03 12:00:00")


def measure(value, minutes_before_now, name="temperature", machine=MACHINE):
	return frappe.get_doc(
		{
			"doctype": "Machine Event",
			"machine": machine,
			"event_type": "Measurement",
			"source": "Manual",
			"measurement_name": name,
			"value": value,
			"timestamp": add_to_date(NOW, minutes=-minutes_before_now),
		}
	).insert(ignore_permissions=True)


def set_settings(**values):
	for field, value in values.items():
		frappe.db.set_single_value("Machine Data Settings", field, value)


class TestSpcMonitor(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine(MACHINE)
		set_settings(
			spc_enabled=1,
			spc_rule_set="Nelson",
			spc_subgroup_size=0,
			spc_baseline_days=7,
			spc_recent_hours=2,
			spc_min_baseline_points=20,
		)
		# 30 in-control readings a day ago, then one spike 30 minutes ago
		for i in range(30):
			measure(10 if i % 2 else 11, 24 * 60 + 30 - i)
		self.spike = measure(30, 30)

	def keys(self, findings):
		return {f["rule_key"] for f in findings}

	def test_settings_defaults_fill_unsaved_values(self):
		frappe.db.delete("Singles", {"doctype": "Machine Data Settings", "field": "spc_recent_hours"})
		frappe.clear_cache(doctype="Machine Data Settings")
		self.assertEqual(spc_settings().spc_recent_hours, 2)
		self.assertEqual(spc_settings().spc_rule_set, "Nelson")

	def test_series_and_pairs(self):
		readings = measurement_series(MACHINE, "temperature", add_to_date(NOW, days=-2))
		self.assertEqual(len(readings), 31)
		self.assertEqual(readings[-1][1], 30.0)
		self.assertEqual(readings, sorted(readings, key=lambda r: r[0]))
		self.assertIn((MACHINE, "temperature"), measured_pairs(add_to_date(NOW, hours=-2)))
		self.assertNotIn((MACHINE, "temperature"), measured_pairs(add_to_date(NOW, minutes=-10)))

	def test_a_spike_raises_a_quality_suggestion_with_evidence(self):
		findings = spc_findings(now=NOW)
		self.assertIn(f"spc:{MACHINE}:temperature:I:N1", self.keys(findings))
		created = raise_suggestions(findings)
		self.assertTrue(created)
		doc = frappe.get_doc("Agent Suggestion", {"rule_key": f"spc:{MACHINE}:temperature:I:N1"})
		self.assertEqual((doc.category, doc.severity, doc.status), ("Quality", "Critical", "Open"))
		self.assertEqual((doc.reference_doctype, doc.reference_name), ("Machine", MACHINE))
		evidence = frappe.parse_json(doc.evidence)
		self.assertEqual(evidence["latest_value"], 30.0)
		self.assertEqual(evidence["baseline_points"], 30)
		# an open suggestion is not raised twice
		self.assertEqual(raise_suggestions(spc_findings(now=NOW)), [])

	def test_a_dismissed_signal_stays_dismissed_until_the_process_signals_again(self):
		raise_suggestions(spc_findings(now=NOW))
		key = f"spc:{MACHINE}:temperature:I:N1"
		doc = frappe.get_doc("Agent Suggestion", {"rule_key": key})
		doc.status = "Dismissed"
		doc.save(ignore_permissions=True)
		doc.db_set("resolved_on", add_to_date(NOW, minutes=-5))
		self.assertNotIn(key, self.keys(spc_findings(now=NOW)))
		measure(31, 2)
		self.assertIn(key, self.keys(spc_findings(now=NOW)))
		raise_suggestions(spc_findings(now=NOW))
		self.assertEqual(frappe.db.get_value("Agent Suggestion", {"rule_key": key}, "status"), "Open")

	def test_settings_refuse_a_bad_subgroup_size(self):
		settings = frappe.get_single("Machine Data Settings")
		settings.spc_subgroup_size = 30
		with self.assertRaises(frappe.ValidationError):
			settings.validate()

	def test_disabled_raises_nothing(self):
		set_settings(spc_enabled=0)
		self.assertEqual(spc_findings(now=NOW), [])

	def test_western_electric_and_xbar_r_settings(self):
		set_settings(spc_rule_set="Western Electric", spc_subgroup_size=5, spc_min_baseline_points=20)
		for i in range(4):
			measure(30 + i, 29 - i)
		keys = self.keys(spc_findings(now=NOW))
		self.assertIn(f"spc:{MACHINE}:temperature:I:WE1", keys)
		self.assertIn(f"spc:{MACHINE}:temperature:X-bar:WE1", keys)
		self.assertFalse([k for k in keys if k.endswith(":N1")])

	def test_findings_run_with_the_built_in_rules(self):
		self.assertIsInstance(collect_findings({}), list)

	def test_control_chart_endpoint(self):
		data = get_control_chart(
			MACHINE,
			"temperature",
			from_date=str(add_to_date(NOW, days=-2)),
			to_date=str(NOW),
			baseline_points=30,
		)
		self.assertEqual(data["chart"], "I")
		self.assertEqual(data["readings"], 31)
		self.assertEqual(data["baseline_points"], 30)
		self.assertAlmostEqual(data["cl"], 10.5)
		self.assertIn("N1", {s["rule"] for s in data["signals"] if s["index"] == 30})
		self.assertEqual(data["secondary"]["chart"], "MR")
		xr = get_control_chart(
			MACHINE,
			"temperature",
			from_date=str(add_to_date(NOW, days=-2)),
			to_date=str(NOW),
			chart="X-bar R",
		)
		self.assertEqual(xr["chart"], "Xbar")
		self.assertEqual(len(xr["points"]), 6)


class TestSpcReport(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine(MACHINE)
		for i in range(30):
			measure(10 if i % 2 else 11, 24 * 60 + 30 - i)
		measure(30, 30)
		self.filters = {
			"machine": MACHINE,
			"measurement": "temperature",
			"from_date": str(add_to_date(NOW, days=-2).date()),
			"to_date": str(NOW.date()),
			"baseline_points": 30,
		}

	def test_individuals_chart(self):
		out = run_report("SPC Control Chart", self.filters, ignore_prepared_report=True)
		rows = out["result"]
		self.assertEqual(len(rows), 31)
		self.assertEqual(rows[-1]["signals"].split(", ")[0], "N1")
		self.assertTrue(rows[0]["in_baseline"])
		self.assertFalse(rows[-1]["in_baseline"])
		self.assertIsNone(rows[0]["spread"])
		self.assertEqual(rows[1]["spread"], 1.0)
		chart = out["chart"]
		self.assertEqual(chart["type"], "line")
		self.assertEqual([d["name"] for d in chart["data"]["datasets"]], ["Value", "UCL", "CL", "LCL"])
		self.assertEqual(len(chart["data"]["labels"]), 31)
		summary = {s["label"]: s["value"] for s in out["report_summary"]}
		self.assertEqual(summary["Readings"], 31)
		self.assertGreaterEqual(summary["Beyond the Limits"], 1)

	def test_xbar_r_chart(self):
		out = run_report(
			"SPC Control Chart",
			{**self.filters, "chart": "X-bar R", "subgroup_size": 5, "baseline_points": 0},
			ignore_prepared_report=True,
		)
		self.assertEqual(len(out["result"]), 6)
		self.assertIsNotNone(out["result"][0]["spread"])

	def test_bad_subgroup_size(self):
		with self.assertRaises(frappe.ValidationError):
			run_report(
				"SPC Control Chart",
				{**self.filters, "chart": "X-bar R", "subgroup_size": 1},
				ignore_prepared_report=True,
			)

	def test_without_a_measurement(self):
		out = run_report("SPC Control Chart", {"machine": MACHINE}, ignore_prepared_report=True)
		self.assertEqual(out["result"], [])
