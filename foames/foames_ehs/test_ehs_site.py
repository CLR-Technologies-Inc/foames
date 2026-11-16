# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""EHS on a site: incidents and their suggestions, permits to work and the lockout check against
machine state, hazard assessments, exposure records, the hourly check and the rates report."""

import frappe
from frappe.utils import add_days, add_to_date, getdate, now_datetime

from foames.foames_ehs.doctype.safety_incident.safety_incident import report_near_miss
from foames.foames_ehs.report.safety_incident_rates.safety_incident_rates import execute as rates_report
from foames.foames_ehs.rules import check_ehs, running_under_lockout
from foames.foames_mes.api import record_events
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user

ISSUER = "ehs-issuer@example.com"
FITTER = "ehs-fitter@example.com"
OPERATOR = "ehs-operator@example.com"


def make_incident(**overrides):
	values = {
		"doctype": "Safety Incident",
		"title": "Hand caught at the infeed",
		"incident_type": "Injury or Illness",
		"occurred_on": add_to_date(now_datetime(), hours=-2),
		"description": "Reached past the guard to clear a jam.",
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_permit(machine="T-EHS", status="Active", hours=8, start=None, points=None, **overrides):
	start = start or add_to_date(now_datetime(), hours=-1)
	values = {
		"doctype": "Safety Permit",
		"permit_type": "Lockout Tagout",
		"machine": machine,
		"work_description": "Replace the infeed belt",
		"status": status,
		"valid_from": start,
		"valid_to": add_to_date(start, hours=hours),
		"issued_by": ISSUER,
		"performed_by": FITTER,
		"isolation_points": points
		if points is not None
		else [{"isolation_point": "Main disconnect", "lock_id": "L-17", "verified": 1}],
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def stamp(dt):
	return dt.strftime("%Y-%m-%dT%H:%M:%S")


def open_safety_suggestions(doctype, name):
	return frappe.get_all(
		"Agent Suggestion",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"status": "Open",
			"category": "Safety",
		},
		fields=["name", "severity", "rule_key"],
	)


class TestSafetyIncident(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-EHS")
		make_user(ISSUER, "FoaMES Safety")
		make_user(FITTER, "FoaMES Maintenance")
		make_user(OPERATOR, "FoaMES Operator")

	def test_recordability_is_worked_out(self):
		first_aid = make_incident(incident_type="First Aid")
		self.assertFalse(first_aid.recordable)
		case = make_incident(days_away=200, medical_treatment=1)
		self.assertTrue(case.recordable)
		self.assertEqual(case.osha_outcome, "Days Away From Work")
		self.assertEqual(case.log_days_away, 180)
		not_work = make_incident(medical_treatment=1, work_related=0)
		self.assertFalse(not_work.recordable)

	def test_impossible_dates_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_incident(occurred_on=add_to_date(now_datetime(), hours=1))
		with self.assertRaises(frappe.ValidationError):
			make_incident(reported_on=add_to_date(now_datetime(), hours=-5))

	def test_serious_incident_raises_and_closing_resolves(self):
		incident = make_incident(medical_treatment=1, machine="T-EHS")
		found = open_safety_suggestions("Safety Incident", incident.name)
		self.assertEqual(len(found), 1)
		self.assertEqual(found[0].severity, "Critical")
		# A minor near miss raises nothing.
		minor = make_incident(incident_type="Near Miss", potential_severity=2)
		self.assertEqual(open_safety_suggestions("Safety Incident", minor.name), [])

		incident.append("actions", {"action": "Fit an interlocked guard", "control_level": "Engineering"})
		incident.save()
		self.assertEqual(incident.status, "Actions Open")

		# A failed save leaves the in-memory document stale, so each attempt starts from the database.
		attempt = frappe.get_doc("Safety Incident", incident.name)
		attempt.status = "Closed"
		with self.assertRaisesRegex(frappe.ValidationError, "root cause"):
			attempt.save()
		attempt = frappe.get_doc("Safety Incident", incident.name)
		attempt.status = "Closed"
		attempt.root_cause = "Guard could be bypassed to clear jams"
		with self.assertRaisesRegex(frappe.ValidationError, "Finish or cancel"):
			attempt.save()
		incident = frappe.get_doc("Safety Incident", incident.name)
		incident.status = "Closed"
		incident.root_cause = "Guard could be bypassed to clear jams"
		incident.actions[0].status = "Done"
		incident.save()
		self.assertEqual(getdate(incident.actions[0].completed_on), getdate())
		self.assertIsNotNone(incident.closed_on)
		self.assertEqual(open_safety_suggestions("Safety Incident", incident.name), [])

	def test_open_actions_move_a_new_report_on(self):
		incident = make_incident(
			incident_type="Unsafe Condition", actions=[{"action": "Tape off the spill", "status": "Open"}]
		)
		self.assertEqual(incident.status, "Actions Open")

	def test_operators_report_near_misses(self):
		with as_user(OPERATOR):
			name = report_near_miss(
				"Forklift nearly hit a pedestrian", "At the dock door", potential_severity=5
			)
		incident = frappe.get_doc("Safety Incident", name)
		self.assertEqual(incident.incident_type, "Near Miss")
		self.assertEqual(incident.reported_by, OPERATOR)
		# Potential severity 5 is a serious-injury precursor even though nobody was hurt.
		self.assertEqual(len(open_safety_suggestions("Safety Incident", name)), 1)

	def test_hourly_check_flags_old_investigations_and_overdue_actions(self):
		old = make_incident(
			incident_type="Near Miss",
			occurred_on=add_days(now_datetime(), -10),
			reported_on=add_days(now_datetime(), -10),
			actions=[{"action": "Add a mirror", "due_on": add_days(getdate(), -3)}],
		)
		check_ehs()
		keys = {s.rule_key for s in open_safety_suggestions("Safety Incident", old.name)}
		self.assertIn(f"ehs-investigation-overdue:{old.name}", keys)
		self.assertTrue(any(k.startswith(f"ehs-action-overdue:{old.name}:") for k in keys))

	def test_rates_report(self):
		make_incident(days_away=3)
		make_incident(incident_type="Near Miss")
		make_incident(incident_type="Near Miss")
		_columns, rows, _, chart, summary = rates_report({"hours_worked": 200000, "machine": None})
		this_month = [r for r in rows if r["month"] == getdate().strftime("%Y-%m")]
		self.assertTrue(this_month)
		self.assertGreaterEqual(this_month[0]["near_miss"], 2)
		self.assertGreaterEqual(this_month[0]["recordable"], 1)
		labels = {s["label"]: s["value"] for s in summary}
		self.assertGreaterEqual(labels["TRIR"], 1.0)
		self.assertIsNotNone(chart)
		_, _, _, _, no_hours = rates_report({})
		self.assertEqual({s["label"]: s["value"] for s in no_hours}["TRIR"], "Enter hours worked")


class TestSafetyPermit(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-EHS")
		make_machine("T-EHS2")
		make_user(ISSUER, "FoaMES Safety")
		make_user(FITTER, "FoaMES Maintenance")

	def test_a_good_permit_activates(self):
		permit = make_permit()
		self.assertEqual(permit.status, "Active")
		self.assertIsNotNone(permit.activated_on)
		self.assertEqual(permit.isolation_points[0].locked_by, "Administrator")

	def test_activation_rules(self):
		with self.assertRaises(frappe.ValidationError):
			make_permit(points=[])
		with self.assertRaises(frappe.ValidationError):
			make_permit(points=[{"isolation_point": "Air valve", "lock_id": "L-2", "verified": 0}])
		with self.assertRaises(frappe.ValidationError):
			make_permit(performed_by=ISSUER)
		with self.assertRaises(frappe.ValidationError):
			make_permit(hours=13)
		# A draft can be prepared incomplete; hot work needs no isolation.
		make_permit(status="Draft", points=[])
		make_permit(permit_type="Hot Work", points=[])

	def test_close_needs_locks_removed_and_never_reopens(self):
		permit = make_permit()
		permit.status = "Closed"
		with self.assertRaisesRegex(frappe.ValidationError, "has not been removed"):
			permit.save()
		permit = frappe.get_doc("Safety Permit", permit.name)
		permit.isolation_points[0].removed_on = now_datetime()
		permit.status = "Closed"
		permit.save()
		self.assertIsNotNone(permit.closed_on)
		permit.status = "Active"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be reopened"):
			permit.save()

	def test_running_under_lockout_is_flagged_at_once(self):
		permit = make_permit()
		make_permit(machine="T-EHS2", permit_type="Hot Work", points=[])
		record_events(
			[{"machine": "T-EHS", "type": "State", "state": "Running", "timestamp": stamp(now_datetime())}]
		)
		found = open_safety_suggestions("Safety Permit", permit.name)
		self.assertEqual(len(found), 1)
		self.assertEqual(found[0].severity, "Critical")
		# No locks on T-EHS2, so running there is fine.
		record_events(
			[{"machine": "T-EHS2", "type": "State", "state": "Running", "timestamp": stamp(now_datetime())}]
		)
		self.assertEqual(
			frappe.db.count(
				"Agent Suggestion",
				{"category": "Safety", "rule_key": ("like", "ehs-running-under-lockout:%")},
			),
			1,
		)
		# The snapshot rule sees the same thing.
		snapshot = {
			"machines": [
				{"name": "T-EHS", "status": "Running", "last_seen": "x"},
				{"name": "T-EHS2", "status": "Running"},
			]
		}
		self.assertEqual([f["reference_name"] for f in running_under_lockout(snapshot)], [permit.name])
		# Removing the lock and closing the permit resolves it.
		permit.isolation_points[0].removed_on = now_datetime()
		permit.status = "Closed"
		permit.save()
		self.assertEqual(open_safety_suggestions("Safety Permit", permit.name), [])

	def test_hourly_check_expires_permits(self):
		permit = make_permit(start=add_to_date(now_datetime(), hours=-10), hours=8)
		check_ehs()
		permit.reload()
		self.assertEqual(permit.status, "Expired")
		found = open_safety_suggestions("Safety Permit", permit.name)
		self.assertEqual([f.severity for f in found], ["Critical"])  # its lock is still on


class TestHazardAndExposure(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-EHS")

	def make_hazard(self, **overrides):
		values = {
			"doctype": "Hazard Assessment",
			"title": "Nip point at the infeed rollers",
			"hazard_type": "Mechanical",
			"machine": "T-EHS",
			"description": "Fingers drawn into the rollers while clearing jams",
			"likelihood": 4,
			"severity": 4,
			"status": "Active",
		}
		values.update(overrides)
		return frappe.get_doc(values).insert()

	def test_risk_is_scored(self):
		hazard = self.make_hazard(
			residual_likelihood=2,
			controls=[
				{"control": "Interlocked guard", "control_level": "Engineering", "in_place": 1},
				{"control": "Cut-resistant gloves", "control_level": "PPE", "in_place": 1},
			],
		)
		self.assertEqual((hazard.risk_score, hazard.risk_level), (16, "High"))
		self.assertEqual((hazard.residual_score, hazard.residual_level), (8, "Medium"))
		self.assertEqual(hazard.strongest_control, "Engineering")
		self.assertEqual(getdate(hazard.next_review_on), add_days(getdate(hazard.reviewed_on), 365))
		with self.assertRaises(frappe.ValidationError):
			self.make_hazard(likelihood=6)
		with self.assertRaises(frappe.ValidationError):
			self.make_hazard(likelihood=2, severity=2, residual_likelihood=3)

	def test_hourly_check_reviews_hazards(self):
		hazard = self.make_hazard(
			reviewed_on=add_days(getdate(), -400),
			controls=[{"control": "Gloves", "control_level": "PPE", "in_place": 1}],
		)
		check_ehs()
		keys = {s.rule_key for s in open_safety_suggestions("Hazard Assessment", hazard.name)}
		self.assertTrue(any(k.startswith(f"ehs-hazard-review:{hazard.name}") for k in keys))
		self.assertTrue(any(k.startswith(f"ehs-hazard-weak-controls:{hazard.name}") for k in keys))

	def test_exposure(self):
		silica = frappe.get_doc(
			{
				"doctype": "Exposure Record",
				"agent": "Respirable crystalline silica",
				"method": "Concentration",
				"unit": "mg/m3",
				"machine": "T-EHS",
				"exposure_group": "Grinding cell",
				"limit": 0.05,
				"action_level": 0.025,
				"samples": [{"minutes": 240, "value": 0.08}, {"minutes": 200, "value": 0.06}],
			}
		).insert()
		self.assertAlmostEqual(silica.result, (0.08 * 240 + 0.06 * 200) / 480, places=4)
		self.assertEqual(silica.status, "Above Limit")
		self.assertEqual(len(open_safety_suggestions("Exposure Record", silica.name)), 1)

		noise = frappe.get_doc(
			{
				"doctype": "Exposure Record",
				"agent": "Noise",
				"method": "Noise",
				"exposure_group": "Press operators",
				"samples": [{"minutes": 480, "value": 87}],
			}
		).insert()
		self.assertEqual(noise.unit, "dBA")
		self.assertEqual((noise.limit, noise.action_level), (90, 85))
		self.assertAlmostEqual(noise.result, 87.0, places=1)
		self.assertEqual(noise.status, "At or Above Action Level")
		self.assertEqual(open_safety_suggestions("Exposure Record", noise.name)[0].severity, "Warning")
