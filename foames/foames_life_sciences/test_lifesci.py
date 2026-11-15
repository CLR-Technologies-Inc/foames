# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Life sciences on a Frappe site: NPI gates and their suggestions, phase reviews, requirements approval and tracing, tech
transfer approval, comparability review, PD studies end to end, and the read API."""

import json

import frappe
from frappe.utils import add_days, getdate, nowdate

from foames.foames_life_sciences import api
from foames.foames_life_sciences.tasks import check_npi_gates
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_user

ENGINEER = "ls-engineer@example.com"
LEAD = "ls-lead@example.com"
QUALITY = "ls-quality@example.com"
OPERATOR = "ls-operator@example.com"
CHAIR = "ls-chair@example.com"
MEMBER_1 = "ls-member-1@example.com"
MEMBER_2 = "ls-member-2@example.com"
# Refused by a rule (ValidationError) or by the role permissions (PermissionError).
REFUSED = (frappe.ValidationError, frappe.PermissionError)


def make_program(**overrides):
	values = {
		"doctype": "NPI Program",
		"title": "Infusion pump NPI",
		"product_name": "Infusion pump",
		"product_type": "Medical Device",
		"program_lead": LEAD,
	}
	values.update(overrides)
	with as_user(ENGINEER):
		return frappe.get_doc(values).insert()


def complete_stage(program, stage):
	for row in program.deliverables:
		if row.stage == stage:
			row.status = "Complete"
	for row in program.criteria:
		if row.stage == stage:
			row.met = 1
	with as_user(ENGINEER):
		program.save()


def make_prd(**overrides):
	values = {
		"doctype": "Product Requirements Document",
		"title": "mAb drug product requirements",
		"product_name": "mAb-1",
		"product_type": "Biologic",
		"requirements": [
			{"req_id": "QT-1", "level": "QTPP Element", "requirement": "Sterile solution for IV use"},
			{
				"req_id": "CQA-1",
				"level": "CQA",
				"parent_req": "QT-1",
				"requirement": "Monomer purity",
				"critical": 1,
				"acceptance_criteria": ">= 95 % by SEC",
				"verification_method": "Test",
			},
		],
	}
	values.update(overrides)
	with as_user(ENGINEER):
		return frappe.get_doc(values).insert()


def make_package(submit=True, **overrides):
	values = {
		"doctype": "Tech Transfer Package",
		"title": "mAb-1 upstream to 2000 L",
		"product_name": "mAb-1",
		"process_name": "Upstream cell culture",
		"transfer_type": "Scale-Up",
		"sending_site": "Pilot plant, 200 L",
		"receiving_site": "Commercial suite, 2000 L",
		"from_scale": 200,
		"to_scale": 2000,
		"parameters": [
			{
				"parameter": "Temperature",
				"unit_of_measure": "C",
				"criticality": "CPP",
				"limits": "Lower and Upper",
				"set_point": 36.8,
				"nor_low": 36.5,
				"nor_high": 37.1,
				"par_low": 35.5,
				"par_high": 37.5,
				"scale_rule": "Scale Independent",
			},
			{
				"parameter": "Feed volume",
				"unit_of_measure": "L",
				"criticality": "KPP",
				"limits": "Lower and Upper",
				"set_point": 10,
				"nor_low": 9,
				"nor_high": 11,
				"par_low": 8,
				"par_high": 12,
				"scale_dependent": 1,
				"scale_rule": "Linear with Volume",
			},
		],
		"attributes": [
			{
				"attribute": "Monomer purity",
				"unit_of_measure": "%",
				"criticality": "CQA",
				"limits": "Lower Only",
				"lower": 95,
				"approach": "Equivalence (TOST)",
				"margin": 1.0,
				"analytical_method": "SEC-HPLC",
			}
		],
	}
	values.update(overrides)
	with as_user(ENGINEER):
		doc = frappe.get_doc(values).insert()
	if submit:
		with as_user(QUALITY):
			doc.submit()
	return doc


class TestNPIProgram(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_user(ENGINEER, "FoaMES Engineer")
		make_user(LEAD, "FoaMES Engineer", "FoaMES Quality")
		make_user(QUALITY, "FoaMES Quality")
		make_user(OPERATOR, "FoaMES Operator")

	def test_new_program_gets_gates_and_template(self):
		program = make_program()
		self.assertEqual(program.current_stage, "Concept")
		self.assertEqual(program.status, "Active")
		self.assertEqual(program.gates[0].stage, "Concept")
		self.assertEqual(len(program.gates), 6)
		self.assertIn("Design history file complete", [d.deliverable for d in program.deliverables])
		drug = make_program(title="Biologic NPI", product_type="Biologic")
		self.assertIn("Quality target product profile (QTPP)", [d.deliverable for d in drug.deliverables])

	def test_stage_and_decisions_cannot_be_edited(self):
		program = make_program()
		program.current_stage = "Launch"
		with as_user(ENGINEER), self.assertRaises(frappe.ValidationError):
			program.save()
		program.reload()
		program.gates[0].decision = "Go"
		with as_user(ENGINEER), self.assertRaises(frappe.ValidationError):
			program.save()

	def test_gate_go_needs_deliverables_and_an_independent_reviewer(self):
		program = make_program()
		with as_user(QUALITY), self.assertRaises(frappe.ValidationError):
			program.record_gate_decision("Go")
		complete_stage(program, "Concept")
		program.reload()
		with as_user(LEAD), self.assertRaises(frappe.ValidationError):
			program.record_gate_decision("Go")
		with as_user(ENGINEER), self.assertRaises(frappe.PermissionError):
			program.record_gate_decision("Go")
		with as_user(QUALITY):
			result = program.record_gate_decision("Go")
		self.assertEqual(result, {"current_stage": "Feasibility", "status": "Active"})
		program.reload()
		self.assertEqual(program.gates[0].decision, "Go")
		self.assertEqual(program.gates[0].decided_by, QUALITY)

	def test_conditional_go_hold_and_kill(self):
		program = make_program()
		complete_stage(program, "Concept")
		program.reload()
		with as_user(QUALITY):
			program.record_gate_decision(
				"Conditional Go", "Close the open usability finding", add_days(nowdate(), 30)
			)
		program.reload()
		self.assertEqual(program.current_stage, "Feasibility")
		with as_user(QUALITY):
			program.close_gate_conditions("Concept")
			program.reload()
			program.record_gate_decision("Hold", "Supplier capacity unknown")
		program.reload()
		self.assertEqual(program.status, "On Hold")
		with as_user(QUALITY):
			program.record_gate_decision("Kill", "Business case withdrawn")
		program.reload()
		self.assertEqual(program.status, "Cancelled")
		with as_user(QUALITY), self.assertRaises(frappe.ValidationError):
			program.record_gate_decision("Go")

	def test_go_needs_exit_criteria(self):
		program = make_program()
		for row in program.deliverables:
			if row.stage == "Concept":
				row.status = "Complete"
		with as_user(ENGINEER):
			program.save()
		with as_user(QUALITY), self.assertRaises(frappe.ValidationError):
			program.record_gate_decision("Go")
		self.assertIn(
			"Go-to-market ready", " ".join(c.criterion for c in program.criteria if c.stage == "Transfer")
		)

	def test_overdue_gate_raises_a_suggestion(self):
		program = make_program()
		program.gates[0].target_date = add_days(nowdate(), -2)
		with as_user(ENGINEER):
			program.save()
		created = check_npi_gates()
		self.assertEqual(len(created), 1)
		suggestion = frappe.get_doc("Agent Suggestion", created[0])
		self.assertEqual(suggestion.reference_name, program.name)
		self.assertIn("overdue", suggestion.title)
		self.assertEqual(check_npi_gates(), [])

	def test_status_api(self):
		program = make_program()
		with as_user(ENGINEER):
			rows = api.get_npi_status(program.name)
		self.assertEqual(rows[0]["current_stage"], "Concept")
		self.assertTrue(rows[0]["current_stage_progress"]["missing_required"])
		with as_user(OPERATOR):
			self.assertEqual(api.get_npi_status(program.name)[0]["name"], program.name)


def make_board(quorum=3):
	return frappe.get_doc(
		{
			"doctype": "Phase Review Board",
			"board_name": "Device portfolio board",
			"quorum": quorum,
			"members": [
				{"user": CHAIR, "board_role": "Chair", "function": "General management"},
				{"user": MEMBER_1, "board_role": "Member", "function": "Quality"},
				{"user": MEMBER_2, "board_role": "Member", "function": "Marketing"},
				{"user": ENGINEER, "board_role": "Advisor", "function": "R&D"},
			],
		}
	).insert()


class TestPhaseReview(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_user(ENGINEER, "FoaMES Engineer")
		make_user(LEAD, "FoaMES Engineer")
		make_user(QUALITY, "FoaMES Quality")
		for user in (CHAIR, MEMBER_1, MEMBER_2):
			make_user(user, "FoaMES Engineer")
		self.board = make_board()

	def open_review(self, program, **votes):
		with as_user(ENGINEER):
			review = frappe.get_doc({"doctype": "Phase Review", "npi_program": program.name}).insert()
		for a in review.attendees:
			a.present = 1
			a.vote = votes.get(a.user)
		with as_user(ENGINEER):
			review.save()
		return review

	def test_board_needs_a_chair_and_a_reachable_quorum(self):
		self.assertEqual(self.board.chair, CHAIR)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Phase Review Board",
					"board_name": "No chair",
					"quorum": 2,
					"members": [{"user": MEMBER_1, "board_role": "Member"}],
				}
			).insert()

	def test_gate_decisions_go_through_the_board(self):
		program = make_program(phase_review_board=self.board.name)
		complete_stage(program, "Concept")
		program.reload()
		with as_user(QUALITY), self.assertRaises(frappe.ValidationError):
			program.record_gate_decision("Go")
		review = self.open_review(program, **{CHAIR: "Go", MEMBER_1: "Go", MEMBER_2: "Recycle"})
		self.assertEqual(review.stage, "Concept")
		self.assertEqual(review.chair, CHAIR)
		self.assertEqual(len(review.attendees), 4)
		self.assertEqual(review.vote_summary, "Go: 2, Recycle: 1")
		review.decision = "Go"
		with as_user(ENGINEER):
			review.save()
		with as_user(MEMBER_1), self.assertRaises(frappe.ValidationError):
			review.submit()
		review.reload()
		with as_user(CHAIR):
			review.submit()
		program.reload()
		self.assertEqual(program.current_stage, "Feasibility")
		self.assertEqual(program.gates[0].phase_review, review.name)
		self.assertEqual(program.gates[0].decided_by, CHAIR)
		self.assertIn("[x] Exit", review.criteria_at_review)

	def test_review_refused_without_quorum_or_entry_criteria(self):
		program = make_program(phase_review_board=self.board.name)
		review = self.open_review(program, **{CHAIR: "Recycle", MEMBER_1: "Recycle"})
		for a in review.attendees:
			if a.user == MEMBER_2:
				a.present = 0
		review.decision = "Recycle"
		review.rationale = "Business case not ready"
		with as_user(ENGINEER):
			review.save()
		with as_user(CHAIR), self.assertRaises(frappe.ValidationError):
			review.submit()
		with as_user(ENGINEER), self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Phase Review", "npi_program": make_program(title="No board").name}
			).insert()

	def test_status_api_lists_reviews_and_criteria(self):
		program = make_program(phase_review_board=self.board.name)
		self.open_review(program)
		with as_user(ENGINEER):
			status = api.get_npi_status(program.name)[0]
		self.assertEqual(status["phase_review_board"], self.board.name)
		self.assertTrue(status["entry_criteria_open"])
		self.assertEqual(len(status["phase_reviews"]), 1)


class TestRequirementsAndTransfer(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_user(ENGINEER, "FoaMES Engineer")
		make_user(QUALITY, "FoaMES Quality")

	def test_prd_rules_and_approval(self):
		with self.assertRaises(frappe.ValidationError):
			make_prd(
				requirements=[{"req_id": "CQA-1", "level": "CQA", "parent_req": "QT-9", "requirement": "x"}]
			)
		prd = make_prd()
		self.assertEqual(prd.prepared_by, ENGINEER)
		self.assertEqual(prd.percent_verified, 0)
		with as_user(ENGINEER), self.assertRaises(REFUSED):
			prd.submit()
		with as_user(QUALITY):
			prd.submit()
		prd.reload()
		self.assertEqual(prd.approved_by, QUALITY)
		prd.requirements[1].verification_status = "Passed"
		prd.requirements[1].verification_reference = "VER-001"
		with as_user(ENGINEER):
			prd.save()
		prd.reload()
		self.assertEqual(prd.percent_verified, 100)
		with as_user(ENGINEER):
			trace = api.get_requirements_trace(prd.name)
		self.assertTrue(trace["approved"])
		self.assertEqual(trace["verified"], 1)

	def test_package_needs_consistency_and_another_approver(self):
		with self.assertRaises(frappe.ValidationError):
			make_package(
				parameters=[
					{
						"parameter": "pH",
						"criticality": "CPP",
						"limits": "Lower and Upper",
						"set_point": 7.0,
						"nor_low": 6.8,
						"nor_high": 7.4,
						"par_low": 6.9,
						"par_high": 7.2,
					}
				]
			)
		draft = make_package(submit=False)
		self.assertEqual(draft.scale_ratio, 10)
		self.assertEqual(draft.parameters[1].receiving_set_point, 100)
		self.assertEqual(draft.parameters[0].receiving_set_point, 36.8)
		self.assertEqual(len(draft.deliverables), 9)
		with as_user(ENGINEER), self.assertRaises(REFUSED):
			draft.submit()
		prd = make_prd()
		draft.product_requirements = prd.name
		draft.attributes[0].requirement_id = "CQA-9"
		with as_user(ENGINEER):
			draft.save()
		with as_user(QUALITY), self.assertRaises(frappe.ValidationError):
			draft.submit()

	def test_comparability_review(self):
		package = make_package()
		results = [
			{"site": "Sending", "batch": f"S{i}", "value": v} for i, v in enumerate((98.1, 99.0, 98.5, 98.7))
		]
		results += [
			{"site": "Receiving", "batch": f"R{i}", "value": v} for i, v in enumerate((98.4, 98.9, 98.2))
		]
		with as_user(ENGINEER):
			assessment = frappe.get_doc(
				{
					"doctype": "Comparability Assessment",
					"tech_transfer_package": package.name,
					"attribute": "Monomer purity",
					"results": results,
				}
			).insert()
		self.assertEqual(assessment.approach, "Equivalence (TOST)")
		self.assertEqual(assessment.outcome, "Comparable")
		self.assertEqual(assessment.receiving_n, 3)
		with as_user(ENGINEER), self.assertRaises(REFUSED):
			assessment.submit()
		with as_user(QUALITY):
			assessment.submit()
		with as_user(ENGINEER):
			view = api.get_tech_transfer_package(package.name)
		self.assertTrue(view["approved"])
		self.assertEqual(view["attributes"][0]["comparability"]["outcome"], "Comparable")
		with as_user(ENGINEER), self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Comparability Assessment",
					"tech_transfer_package": package.name,
					"attribute": "Titer",
					"results": results,
				}
			).insert()


class TestPDSimulationStudy(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_user(ENGINEER, "FoaMES Engineer")

	def make_study(self):
		with as_user(ENGINEER):
			return frappe.get_doc(
				{
					"doctype": "PD Simulation Study",
					"title": "Production bioreactor CPP ranges",
					"process_name": "Upstream cell culture",
					"design_type": "Central Composite (Face-Centred)",
					"center_points": 3,
					"randomise": 1,
					"seed": 11,
					"model_type": "Quadratic",
					"iterations": 500,
					"factors": [
						{"factor": "Temperature", "low": 35, "high": 37, "distribution": "Normal", "sd": 0.2},
						{"factor": "pH", "low": 6.9, "high": 7.3, "nominal": "7.1"},
					],
					"responses": [
						{"response": "Titer", "unit_of_measure": "g/L", "limits": "Lower Only", "lower": 3}
					],
				}
			).insert()

	def test_end_to_end(self):
		study = self.make_study()
		self.assertEqual(study.status, "Planning")
		self.assertEqual([f.symbol for f in study.factors], ["x1", "x2"])
		with as_user(ENGINEER):
			summary = study.generate_design()
		self.assertIn("11 runs", summary)
		study.reload()
		for run in study.runs:
			t = (2 * run.x1 - 72) / 2
			ph = (2 * run.x2 - 14.2) / 0.4
			run.y1 = str(round(4 + 0.5 * t - 0.3 * ph - 0.4 * t * t, 6))
		with as_user(ENGINEER):
			study.save()
			study.fit_models()
		study.reload()
		self.assertEqual(study.status, "Modelled")
		models = json.loads(study.model_results)["models"]
		self.assertAlmostEqual(models["Titer"]["r_squared"], 1.0, places=6)
		with as_user(ENGINEER):
			result = study.run_what_if()
			space = study.get_design_space("Temperature", "pH", 5)
		self.assertEqual(result["iterations"], 500)
		self.assertGreater(study.probability_all_in_limits, 0)
		self.assertEqual(len(space["grid"]), 5)
		with as_user(ENGINEER):
			view = api.get_pd_study(study.name)
			self.assertEqual(len(view["runs"]), 11)
			self.assertIsNotNone(view["models"])
			with self.assertRaises(frappe.ValidationError):
				study.generate_design()

	def test_validation(self):
		with as_user(ENGINEER), self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "PD Simulation Study",
					"title": "Bad",
					"factors": [{"factor": "T", "low": 5, "high": 1}],
				}
			).insert()

	def test_scale_up_api(self):
		result = api.scale_up(2, 2000, 0.05, 300, tank_diameter_m=0.13, gas_l_min=0.2)
		self.assertAlmostEqual(result["length_ratio"], 10.0)
		with self.assertRaises(frappe.ValidationError):
			api.scale_up(0, 2000, 0.05, 300)
