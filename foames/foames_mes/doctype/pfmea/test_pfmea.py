# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from foames.foames_mes.api import record_events
from foames.foames_mes.doctype.pfmea.pfmea import check_pfmeas, observe, observe_now
from foames.foames_mes.report.pfmea_control_plan.pfmea_control_plan import execute as control_plan
from foames.foames_mes.report.pfmea_risk_register.pfmea_risk_register import execute as risk_register
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_reason, make_user


def stamp(days_ago):
	return add_days(now_datetime(), -days_ago).strftime("%Y-%m-%dT%H:%M:%S")


def row(**overrides):
	values = {
		"op_no": "20",
		"process_step": "Press fit bearing",
		"machine": "T-FMEA",
		"function_requirement": "Bearing seated to 0.05 mm",
		"failure_effect": "Noise at the end user; rework at the plant",
		"severity": 7,
		"failure_mode": "Bearing not seated",
		"failure_cause": "Press force below setpoint",
		"prevention_controls": "Force setpoint locked",
		"occurrence": 3,
		"detection_controls": "Force-distance monitoring",
		"detection": 6,
	}
	values.update(overrides)
	return values


def make_pfmea(*rows, **overrides):
	values = {
		"doctype": "PFMEA",
		"title": "Housing line",
		"process_line": "T-LINE-FMEA",
		"items": list(rows) or [row()],
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


class TestPFMEA(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-FMEA")

	# Ratings and validation

	def test_action_priority_and_rpn_are_computed(self):
		doc = make_pfmea(
			row(), row(severity=9, occurrence=6, detection=5), row(severity=2, occurrence=2, detection=2)
		)
		self.assertEqual([r.action_priority for r in doc.items], ["M", "H", "L"])
		self.assertEqual(doc.items[0].rpn, 126)
		self.assertEqual((doc.high_count, doc.medium_count, doc.low_count), (1, 1, 1))
		self.assertEqual(doc.observation_days, 90)

	def test_draft_rows_may_wait_for_ratings_but_release_may_not(self):
		doc = make_pfmea(row(occurrence=None, detection=None))
		self.assertFalse(doc.items[0].action_priority)
		doc.status = "Released"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		doc.status = "Released"
		doc.items[0].occurrence, doc.items[0].detection = 3, 6
		doc.save()
		self.assertTrue(doc.revision_date)

	def test_bad_ratings_and_incomplete_actions_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_pfmea(row(severity=11))
		with self.assertRaises(frappe.ValidationError):
			make_pfmea(row(prevention_action="Poka-yoke", action_status="Completed"))
		with self.assertRaises(frappe.ValidationError):
			make_pfmea(row(machine=None, scrap_counter="reject_unseated"))

	def test_completed_action_is_rerated(self):
		doc = make_pfmea(
			row(
				severity=8,
				occurrence=6,
				detection=6,
				prevention_action="Error-proof the nest",
				action_status="Completed",
				completion_date="2026-11-01",
				new_severity=8,
				new_occurrence=2,
				new_detection=6,
				action_taken="Nest changed, trial of 500 parts clean",
			)
		)
		self.assertEqual((doc.items[0].action_priority, doc.items[0].new_action_priority), ("H", "M"))
		self.assertEqual(doc.open_actions, 0)

	def test_names_are_normalized(self):
		doc = make_pfmea(row(scrap_counter=" Reject_Unseated ", measurement_name=" press_force "))
		self.assertEqual(
			(doc.items[0].scrap_counter, doc.items[0].measurement_name), ("reject_unseated", "press_force")
		)

	# Observation

	def produce(self):
		"""1,000 units in the window, 5 of them rejected on the row's own counter (5 per thousand)."""
		events = []
		for counter, first, last in (("good", 0, 995), ("scrap", 0, 5), ("reject_unseated", 0, 5)):
			events.append(
				{
					"machine": "T-FMEA",
					"type": "Count",
					"counter": counter,
					"value": first,
					"timestamp": stamp(3),
				}
			)
			events.append(
				{
					"machine": "T-FMEA",
					"type": "Count",
					"counter": counter,
					"value": last,
					"timestamp": stamp(2),
				}
			)
		record_events(events)

	def test_scrap_counter_gives_the_observed_occurrence(self):
		self.produce()
		doc = make_pfmea(row(scrap_counter="reject_unseated"), row(failure_mode="No observation"))
		(observed, quiet) = observe(doc.name)
		self.assertAlmostEqual(observed["observed_units"], 1000)
		self.assertAlmostEqual(observed["observed_incidents"], 5)
		self.assertAlmostEqual(observed["observed_per_thousand"], 5.0)
		self.assertEqual(observed["observed_occurrence"], 6)
		self.assertIsNone(quiet["observed_occurrence"])
		stored = frappe.db.get_value(
			"PFMEA Item", observed["row"], ["observed_occurrence", "observed_on"], as_dict=True
		)
		self.assertEqual(stored.observed_occurrence, 6)
		self.assertTrue(stored.observed_on)
		self.assertTrue(frappe.db.get_value("PFMEA", doc.name, "last_observed"))

	def test_downtime_records_count_as_incidents(self):
		self.produce()
		reason = make_reason("T-FMEA-JAM")
		for days_ago in (2, 1):
			frappe.get_doc(
				{
					"doctype": "Downtime Record",
					"machine": "T-FMEA",
					"reason": reason.name,
					"source": "Manual",
					"start_time": add_days(now_datetime(), -days_ago),
					"end_time": add_to_date(add_days(now_datetime(), -days_ago), minutes=10),
				}
			).insert()
		doc = make_pfmea(row(downtime_reason=reason.name))
		(observed,) = observe(doc.name)
		self.assertEqual(observed["observed_incidents"], 2)
		self.assertEqual(observed["observed_occurrence"], 6)  # 2 per thousand

	def test_spc_suggestions_are_counted_for_the_measurement(self):
		latest = add_days(now_datetime(), -1)
		for key in (
			"spc:T-FMEA:press_force:imr:N1",
			"spc:T-FMEA:press_force:imr:N2",
			"spc:T-FMEA:press_force_peak:imr:N1",
			"spc:OTHER:press_force:imr:N1",
		):
			frappe.get_doc(
				{
					"doctype": "Agent Suggestion",
					"title": key,
					"suggestion": "An SPC signal",
					"category": "Quality",
					"severity": "Warning",
					"rule_key": key,
					"evidence": frappe.as_json({"latest_signal_at": str(latest)}),
				}
			).insert(ignore_permissions=True)
		doc = make_pfmea(row(measurement_name="press_force"))
		(observed,) = observe(doc.name)
		self.assertEqual(observed["spc_signals"], 2)
		self.assertTrue(observed["latest_signal_at"].startswith(str(latest)[:16]))
		line_wide = make_pfmea(row(machine=None, measurement_name="press_force"))
		self.assertEqual(observe(line_wide.name)[0]["spc_signals"], 3)

	# Suggestions

	def test_check_raises_review_suggestions_for_released_pfmeas_only(self):
		self.produce()
		draft = make_pfmea(row(scrap_counter="reject_unseated"))
		self.assertEqual(check_pfmeas(), [])
		released = make_pfmea(
			row(scrap_counter="reject_unseated"),
			row(failure_mode="Wrong bearing", severity=9, occurrence=6, detection=5),
			row(
				failure_mode="Cracked race",
				detection_action="Add acoustic check",
				target_date=add_days(nowdate(), -3),
				action_status="Open",
			),
			status="Released",
		)
		raised = check_pfmeas()
		self.assertEqual(len(raised), 3)
		keys = {frappe.db.get_value("Agent Suggestion", n, "rule_key") for n in raised}
		self.assertEqual(
			{k.split(":")[3] for k in keys}, {"occurrence", "high-without-action", "overdue"}, keys
		)
		(occurrence,) = frappe.get_all(
			"Agent Suggestion",
			filters={"name": ("in", raised), "rule_key": ("like", "%:occurrence:%")},
			fields=["severity", "reference_name"],
		)
		# S7 at observed O6 with D6 is High.
		self.assertEqual((occurrence.severity, occurrence.reference_name), ("Critical", released.name))
		self.assertEqual(check_pfmeas(), [])
		self.assertNotIn(
			draft.name, {frappe.db.get_value("Agent Suggestion", n, "reference_name") for n in raised}
		)

	def test_observe_now_needs_write_permission(self):
		doc = make_pfmea()
		make_user("t-fmea-operator@example.com", "FoaMES Operator")
		with as_user("t-fmea-operator@example.com"):
			with self.assertRaises(frappe.PermissionError):
				observe_now(doc.name)
		self.assertEqual(observe_now(doc.name)["rows"], 1)

	# Reports

	def test_reports(self):
		doc = make_pfmea(
			row(
				special_characteristic="SC",
				reaction_plan="Contain and 100% check",
				measurement_name="press_force",
			),
			row(failure_mode="Wrong bearing", severity=9, occurrence=6, detection=5),
			row(
				failure_mode="Burr",
				severity=2,
				occurrence=2,
				detection=2,
				prevention_action="Deburr",
				action_status="Open",
			),
		)
		_c, rows, _msg, chart, summary = risk_register({"pfmea": doc.name})
		self.assertEqual([r["action_priority"] for r in rows], ["H", "M", "L"])
		self.assertEqual(summary[0]["value"], 1)
		self.assertTrue(chart)
		_c, open_rows, *_ = risk_register({"pfmea": doc.name, "open_actions_only": 1})
		self.assertEqual([r["failure_mode"] for r in open_rows], ["Burr"])
		_c, high, *_ = risk_register({"pfmea": doc.name, "action_priority": "H"})
		self.assertEqual(len(high), 1)

		_c, plan = control_plan({"pfmea": doc.name})
		self.assertEqual([r["failure_mode"] for r in plan], ["Bearing not seated", "Wrong bearing", "Burr"])
		self.assertEqual(plan[0]["reaction_plan"], "Contain and 100% check")
		_c, special = control_plan({"pfmea": doc.name, "special_only": 1})
		self.assertEqual(len(special), 1)

		doc.status = "Obsolete"
		doc.save()
		self.assertFalse(
			[r for r in risk_register({"process_line": "T-LINE-FMEA"})[1] if r["pfmea"] == doc.name]
		)
