# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe.utils import add_days, getdate, nowdate

from foames.foames_risk.doctype.enterprise_risk.enterprise_risk import (
	accept_residual_risk,
	create_from_template,
	record_review,
)
from foames.foames_risk.register import check_risks, collect_findings, create_defaults, linkable_doctypes
from foames.foames_risk.report.risk_heat_map.risk_heat_map import execute as heat_map
from foames.foames_risk.report.risk_register.risk_register import execute as register
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, enforcing_roles, make_machine, make_user

DOCTYPE = "Enterprise Risk"
ENGINEER = "risk-engineer@example.com"
SUPERVISOR = "risk-supervisor@example.com"


def make_risk(**overrides):
	values = {
		"doctype": DOCTYPE,
		"title": "Solvent vapour at the mixing vessel",
		"category": "Safety and Health",
		"objective": "Operations",
		"risk_statement": "If solvent vapour builds up at the mixing vessel, then workers may be overcome.",
		"inherent_impact": 5,
		"inherent_likelihood": 4,
		"response": "Reduce",
		"residual_impact": 4,
		"residual_likelihood": 2,
		"controls": [
			{
				"control": "Local exhaust ventilation at the charging port",
				"control_level": "Engineering Controls",
				"status": "In Place",
				"implemented_on": add_days(nowdate(), -30),
			}
		],
	}
	values.update(overrides)
	with as_user(ENGINEER):
		return frappe.get_doc(values).insert()


class TestEnterpriseRisk(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		create_defaults()
		make_user(ENGINEER, "FoaMES Engineer")
		make_user(SUPERVISOR, "FoaMES Supervisor")

	def test_defaults_installed_once(self):
		self.assertTrue(frappe.db.exists("Risk Category", "Safety and Health"))
		count = frappe.db.count("Risk Template")
		self.assertGreaterEqual(count, 10)
		create_defaults()
		self.assertEqual(frappe.db.count("Risk Template"), count)

	def test_scores_ratings_and_tolerance(self):
		doc = make_risk()
		self.assertEqual(doc.inherent_score, 20)
		self.assertEqual(doc.inherent_rating, "Very High")
		self.assertEqual(doc.residual_score, 8)
		self.assertEqual(doc.residual_rating, "Moderate")
		# Safety and Health tolerates Low by default.
		self.assertEqual(doc.tolerance, "Low")
		self.assertFalse(doc.within_tolerance)
		self.assertEqual(doc.strongest_control, "Engineering Controls")
		self.assertEqual(doc.controls_in_place, 1)
		self.assertEqual(getdate(doc.next_review_on), add_days(getdate(doc.identified_on), 365))
		self.assertIsNotNone(doc.controls[0].next_verification_on)

	def test_residual_above_inherent_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_risk(residual_impact=5, residual_likelihood=5)

	def test_reduction_without_controls_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_risk(controls=[])

	def test_transfer_needs_counterparty(self):
		with self.assertRaises(frappe.ValidationError):
			make_risk(response="Transfer", controls=[])
		doc = make_risk(response="Transfer", controls=[], transfer_to="Property insurer")
		self.assertEqual(doc.residual_score, 8)

	def test_acceptance_is_recorded_and_cleared_by_a_new_score(self):
		doc = make_risk()
		with self.assertRaises(frappe.ValidationError):
			doc.status = "Monitoring"
			with as_user(ENGINEER):
				doc.save()
		doc.reload()
		# Typing the acceptance into the record does not count.
		doc.accepted_by = ENGINEER
		with as_user(ENGINEER):
			doc.save()
		self.assertIsNone(doc.accepted_by)
		with as_user(ENGINEER), enforcing_roles(), self.assertRaises(frappe.PermissionError):
			accept_residual_risk(doc.name, "Business need")
		with as_user(SUPERVISOR), enforcing_roles():
			accept_residual_risk(doc.name, "Vessel replaced next quarter")
		doc.reload()
		self.assertEqual(doc.accepted_by, SUPERVISOR)
		self.assertEqual(doc.accepted_score, 8)
		doc.status = "Monitoring"
		with as_user(ENGINEER):
			doc.save()
		# A new residual score needs a new acceptance before the risk can stay in Monitoring.
		doc.residual_likelihood = 3
		with as_user(ENGINEER), self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		doc.residual_likelihood = 3
		doc.status = "Treating"
		with as_user(ENGINEER):
			doc.save()
		self.assertIsNone(doc.accepted_by)

	def test_review_history(self):
		doc = make_risk()
		with as_user(ENGINEER):
			record_review(doc.name, "Ventilation checked")
		doc.reload()
		self.assertEqual(getdate(doc.last_reviewed_on), getdate(nowdate()))
		self.assertEqual(len(doc.reviews), 1)
		self.assertEqual(doc.reviews[0].reviewed_by, ENGINEER)
		# History cannot be edited by saving the form.
		doc.set("reviews", [])
		with as_user(ENGINEER):
			doc.save()
		self.assertEqual(len(doc.reviews), 1)

	def test_verification_records_who(self):
		doc = make_risk()
		doc.controls[0].verification_result = "Pass"
		with as_user(ENGINEER):
			doc.save()
		self.assertEqual(doc.controls[0].verified_by, ENGINEER)
		self.assertEqual(getdate(doc.controls[0].verified_on), getdate(nowdate()))

	def test_links_only_to_known_types(self):
		machine = make_machine("RISK-M1")
		self.assertIn("Machine", linkable_doctypes())
		doc = make_risk(links=[{"link_doctype": "Machine", "link_name": machine.name, "relation": "Related"}])
		self.assertEqual(len(doc.links), 1)
		with self.assertRaises(frappe.ValidationError):
			make_risk(links=[{"link_doctype": "User", "link_name": ENGINEER, "relation": "Related"}])

	def test_evidence_on_a_maintenance_plan(self):
		machine = make_machine("RISK-M2")
		plan = frappe.get_doc(
			{
				"doctype": "Maintenance Plan",
				"title": "Check extraction fan",
				"machine": machine.name,
				"trigger_type": "Calendar",
				"interval": 30,
			}
		).insert(ignore_permissions=True)
		doc = make_risk()
		doc.controls[0].evidence_doctype = "Maintenance Plan"
		doc.controls[0].evidence_name = plan.name
		with as_user(ENGINEER):
			doc.save()
		frappe.db.set_value("Maintenance Plan", plan.name, "disabled", 1)
		found = [f for f in collect_findings() if f["reference_name"] == doc.name]
		self.assertTrue(any(":evidence:" in f["rule_key"] for f in found))

	def test_check_raises_suggestions_once(self):
		doc = make_risk()
		created = check_risks()
		keys = frappe.get_all(
			"Agent Suggestion", filters={"reference_name": doc.name, "status": "Open"}, pluck="rule_key"
		)
		self.assertIn(f"risk:tolerance:{doc.name}", keys)
		self.assertTrue(created)
		again = check_risks()
		self.assertFalse(set(again) & set(created))

	def test_template(self):
		with as_user(ENGINEER):
			name = create_from_template("Contact with moving machine parts")
		doc = frappe.get_doc(DOCTYPE, name)
		self.assertEqual(doc.category, "Safety and Health")
		self.assertTrue(doc.controls)
		self.assertTrue(all(c.status == "Planned" for c in doc.controls))
		self.assertEqual(doc.residual_score, doc.inherent_score)

	def test_reports(self):
		make_risk()
		columns, rows, _msg, _chart, summary = register({})
		self.assertTrue(summary)
		self.assertTrue(any(r.title == "Solvent vapour at the mixing vessel" for r in rows))
		self.assertTrue(columns)
		_columns, grid, *_rest = heat_map({"basis": "Residual"})
		self.assertEqual(len(grid), 5)
		row = next(r for r in grid if r["impact"] == 4)
		self.assertGreaterEqual(row["l2"], 1)

	def test_closing_needs_a_note(self):
		doc = make_risk()
		doc.status = "Closed"
		with as_user(ENGINEER), self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.closure_note = "Process retired"
		with as_user(ENGINEER):
			doc.save()
