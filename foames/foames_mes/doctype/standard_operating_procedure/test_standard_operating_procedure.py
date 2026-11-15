# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, add_months, getdate, nowdate

from foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure import (
	acknowledge,
	check_sops,
	get_effective_sops,
	new_revision,
	operator_sop_gaps,
	record_review,
	record_training,
	reject,
	retire,
	sign,
	submit_for_review,
)
from foames.foames_mes.report.sop_training_matrix.sop_training_matrix import execute as training_matrix
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, enforcing_roles, make_machine, make_user

DOCTYPE = "Standard Operating Procedure"
AUTHOR = "sop-author@example.com"
SUPERVISOR = "sop-supervisor@example.com"
QUALITY = "sop-quality@example.com"
OPERATOR = "sop-operator@example.com"
OPERATOR_2 = "sop-operator-2@example.com"


def make_sop(code="SOP-T-001", **overrides):
	values = {
		"doctype": DOCTYPE,
		"sop_code": code,
		"title": "Die change on the transfer press",
		"procedure": "<ol><li>Lock out.</li><li>Change the die.</li></ol>",
		"approvals": [{"role": "FoaMES Supervisor"}, {"role": "FoaMES Quality"}],
		"training_roles": [{"role": "FoaMES Operator"}],
	}
	values.update(overrides)
	with as_user(AUTHOR):
		return frappe.get_doc(values).insert()


def approve(name):
	"""Send for review as the author and sign as the supervisor and quality."""
	with as_user(AUTHOR):
		submit_for_review(name)
	with as_user(SUPERVISOR):
		sign(name)
	with as_user(QUALITY):
		return sign(name, comment="Fit for use")


class TestStandardOperatingProcedure(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_user(AUTHOR, "FoaMES Engineer")
		make_user(SUPERVISOR, "FoaMES Supervisor")
		make_user(QUALITY, "FoaMES Quality")
		make_user(OPERATOR, "FoaMES Operator")
		make_user(OPERATOR_2, "FoaMES Operator")
		make_machine("T-SOP-1", line="T-SOP-LINE")
		make_machine("T-SOP-2", line="T-SOP-LINE")
		make_machine("T-SOP-3", line="T-SOP-OTHER")

	# Creating and naming

	def test_new_sop_is_a_draft_named_by_code_and_revision(self):
		sop = make_sop(" sop-t-001 ")
		self.assertEqual(sop.name, "SOP-T-001-R1")
		self.assertEqual(sop.sop_code, "SOP-T-001")
		self.assertEqual(sop.revision, 1)
		self.assertEqual(sop.status, "Draft")
		self.assertEqual(sop.prepared_by, AUTHOR)

	def test_status_cannot_be_set_by_editing(self):
		sop = make_sop()
		sop.status = "Effective"
		with self.assertRaises(frappe.ValidationError):
			sop.save()

	def test_a_bad_code_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_sop("SOP#1")

	# Review and sign-off

	def test_review_needs_sign_off_rows(self):
		sop = make_sop(approvals=[])
		with as_user(AUTHOR), self.assertRaises(frappe.ValidationError):
			submit_for_review(sop.name)

	def test_content_is_locked_in_review(self):
		sop = make_sop()
		with as_user(AUTHOR):
			submit_for_review(sop.name)
			doc = frappe.get_doc(DOCTYPE, sop.name)
			doc.procedure = "<p>Something else</p>"
			with self.assertRaises(frappe.ValidationError):
				doc.save()

	def test_signatures_cannot_be_written_directly(self):
		sop = make_sop()
		with as_user(AUTHOR):
			submit_for_review(sop.name)
			doc = frappe.get_doc(DOCTYPE, sop.name)
			doc.approvals[0].signed_by = SUPERVISOR
			with self.assertRaises(frappe.ValidationError):
				doc.save()

	def test_author_cannot_sign_and_nobody_signs_twice(self):
		sop = make_sop()
		make_user("sop-both@example.com", "FoaMES Supervisor", "FoaMES Quality")
		with as_user(AUTHOR):
			submit_for_review(sop.name)
		with as_user(AUTHOR), self.assertRaises(frappe.PermissionError):
			sign(sop.name)
		with as_user("sop-both@example.com"):
			result = sign(sop.name)
			self.assertEqual(result["status"], "In Review")
			self.assertEqual(result["missing"], ["FoaMES Quality"])
			with self.assertRaises(frappe.PermissionError):
				sign(sop.name)
		with as_user(OPERATOR), self.assertRaises(frappe.PermissionError):
			sign(sop.name)

	def test_full_sign_off_makes_it_effective_today(self):
		sop = make_sop()
		result = approve(sop.name)
		self.assertEqual(result["status"], "Effective")
		doc = frappe.get_doc(DOCTYPE, sop.name)
		self.assertEqual(getdate(doc.effective_on), getdate(nowdate()))
		self.assertEqual(getdate(doc.next_review_on), getdate(add_months(nowdate(), 12)))
		self.assertEqual(doc.review_status, "Current")
		self.assertEqual(doc.approvals[1].signed_by, QUALITY)
		self.assertEqual(doc.approvals[1].comment, "Fit for use")
		self.assertIsNotNone(doc.approvals[0].signed_on)

	def test_reject_returns_to_draft_and_clears_signatures(self):
		sop = make_sop()
		with as_user(AUTHOR):
			submit_for_review(sop.name)
		with as_user(SUPERVISOR):
			sign(sop.name)
		with as_user(QUALITY):
			with self.assertRaises(frappe.ValidationError):
				reject(sop.name, "")
			self.assertEqual(reject(sop.name, "Step 2 lacks the torque")["status"], "Draft")
		doc = frappe.get_doc(DOCTYPE, sop.name)
		self.assertFalse(any(row.signed_by for row in doc.approvals))
		with as_user(AUTHOR):
			doc.procedure = "<ol><li>Lock out.</li><li>Change the die; torque to 80 N m.</li></ol>"
			doc.save()

	def test_future_effective_date_waits_for_the_daily_check(self):
		effective = add_days(nowdate(), 5)
		sop = make_sop(effective_on=effective)
		self.assertEqual(approve(sop.name)["status"], "Approved")
		check_sops(today=add_days(nowdate(), 1))
		self.assertEqual(frappe.db.get_value(DOCTYPE, sop.name, "status"), "Approved")
		check_sops(today=effective)
		self.assertEqual(frappe.db.get_value(DOCTYPE, sop.name, "status"), "Effective")

	# Revisions

	def test_new_revision_supersedes_the_effective_one(self):
		r1 = make_sop()
		approve(r1.name)
		with as_user(AUTHOR):
			r2 = new_revision(r1.name)
		self.assertEqual(r2, "SOP-T-001-R2")
		doc = frappe.get_doc(DOCTYPE, r2)
		self.assertEqual((doc.status, doc.revision, doc.supersedes), ("Draft", 2, r1.name))
		self.assertFalse(any(row.signed_by for row in doc.approvals))
		self.assertEqual(len(doc.training_roles), 1)
		with as_user(AUTHOR):
			with self.assertRaises(frappe.ValidationError):
				submit_for_review(r2)
			doc.change_summary = "Added the torque value"
			doc.save()
		approve(r2)
		self.assertEqual(frappe.db.get_value(DOCTYPE, r2, "status"), "Effective")
		old = frappe.get_doc(DOCTYPE, r1.name)
		self.assertEqual((old.status, old.superseded_by), ("Superseded", r2))

	def test_only_one_revision_in_progress(self):
		r1 = make_sop()
		approve(r1.name)
		with as_user(AUTHOR):
			new_revision(r1.name)
			with self.assertRaises(frappe.ValidationError):
				new_revision(r1.name)

	def test_effective_content_is_locked(self):
		sop = make_sop()
		approve(sop.name)
		with as_user(AUTHOR):
			doc = frappe.get_doc(DOCTYPE, sop.name)
			doc.title = "Renamed"
			with self.assertRaises(frappe.ValidationError):
				doc.save()

	def test_retire(self):
		sop = make_sop()
		approve(sop.name)
		with as_user(AUTHOR):
			with self.assertRaises(frappe.ValidationError):
				retire(sop.name, " ")
			self.assertEqual(retire(sop.name, "Press scrapped")["status"], "Obsolete")
			with self.assertRaises(frappe.ValidationError):
				retire(sop.name, "again")
		self.assertNotIn(sop.name, {s["name"] for s in get_effective_sops()})

	# Where it applies

	def test_effective_sops_at_a_machine(self):
		site = make_sop("SOP-T-SITE")
		line = make_sop("SOP-T-LINE", applies_to=[{"line": "T-SOP-LINE"}])
		machine = make_sop("SOP-T-M3", applies_to=[{"machine": "T-SOP-3"}])
		draft = make_sop("SOP-T-DRAFT")
		for sop in (site, line, machine):
			approve(sop.name)
		at_2 = {s["name"] for s in get_effective_sops("T-SOP-2")}
		at_3 = {s["name"] for s in get_effective_sops("T-SOP-3")}
		self.assertTrue({site.name, line.name} <= at_2)
		self.assertNotIn(machine.name, at_2)
		self.assertTrue({site.name, machine.name} <= at_3)
		self.assertNotIn(line.name, at_3)
		self.assertNotIn(draft.name, {s["name"] for s in get_effective_sops()})

	def test_an_applicability_row_must_name_something(self):
		with self.assertRaises(frappe.ValidationError):
			make_sop(applies_to=[{"note": "somewhere"}])

	# Acknowledgement and training

	def test_acknowledgement_follows_the_revision(self):
		r1 = make_sop(applies_to=[{"machine": "T-SOP-1"}])
		with as_user(OPERATOR), self.assertRaises(frappe.ValidationError):
			acknowledge(r1.name)
		approve(r1.name)
		with as_user(OPERATOR):
			self.assertEqual(
				[(g["name"], g["status"]) for g in operator_sop_gaps(machine="T-SOP-1")],
				[(r1.name, "Missing")],
			)
			acknowledge(r1.name)
			acknowledge(r1.name)  # twice is harmless
			self.assertEqual(operator_sop_gaps(machine="T-SOP-1"), [])
		self.assertEqual(frappe.db.count("SOP Acknowledgement", {"sop": r1.name, "user": OPERATOR}), 1)

		with as_user(AUTHOR):
			r2 = new_revision(r1.name)
			doc = frappe.get_doc(DOCTYPE, r2)
			doc.change_summary = "New guard"
			doc.save()
		approve(r2)
		with as_user(OPERATOR):
			self.assertEqual(
				[(g["name"], g["status"]) for g in operator_sop_gaps(machine="T-SOP-1")], [(r2, "Outdated")]
			)
			with self.assertRaises(frappe.ValidationError):
				acknowledge(r1.name)  # superseded
		# Someone outside the training roles has nothing to acknowledge.
		with as_user(SUPERVISOR):
			self.assertEqual(operator_sop_gaps(machine="T-SOP-1"), [])

	def test_trainer_records_training_for_someone_else(self):
		sop = make_sop()
		approve(sop.name)
		with as_user(SUPERVISOR):
			result = record_training(sop.name, OPERATOR_2, "Trained and Assessed", note="Practical on line 1")
		ack = frappe.get_doc("SOP Acknowledgement", result["name"])
		self.assertEqual(
			(ack.user, ack.method, ack.recorded_by, ack.revision),
			(OPERATOR_2, "Trained and Assessed", SUPERVISOR, 1),
		)
		with as_user(OPERATOR), enforcing_roles(), self.assertRaises(frappe.PermissionError):
			record_training(sop.name, OPERATOR_2)
		with as_user(OPERATOR), enforcing_roles(), self.assertRaises(frappe.PermissionError):
			operator_sop_gaps(user=OPERATOR_2)

	def test_training_matrix_report(self):
		sop = make_sop("SOP-T-MATRIX")
		approve(sop.name)
		with as_user(OPERATOR):
			acknowledge(sop.name)
		_columns, rows, *_ = training_matrix({"sop_code": "sop-t-matrix"})
		status = {r["user"]: r["status"] for r in rows}
		self.assertEqual(status[OPERATOR], "Current")
		self.assertEqual(status[OPERATOR_2], "Missing")
		self.assertNotIn(SUPERVISOR, status)
		_c, missing, *_ = training_matrix({"sop_code": "SOP-T-MATRIX", "status": "Missing"})
		self.assertIn(OPERATOR_2, {r["user"] for r in missing})
		self.assertNotIn(OPERATOR, {r["user"] for r in missing})

	# The daily check

	def test_daily_check_raises_training_and_review_suggestions(self):
		sop = make_sop("SOP-T-DAILY", acknowledge_within_days=7, review_interval_months=6)
		approve(sop.name)
		with as_user(OPERATOR):
			acknowledge(sop.name)

		check_sops(today=add_days(nowdate(), 3))
		self.assertFalse(frappe.db.exists("Agent Suggestion", {"rule_key": f"sop-training:{sop.name}"}))

		check_sops(today=add_days(nowdate(), 8))
		suggestion = frappe.get_doc("Agent Suggestion", {"rule_key": f"sop-training:{sop.name}"})
		self.assertEqual((suggestion.status, suggestion.category), ("Open", "Quality"))
		self.assertIn(OPERATOR_2, suggestion.evidence)
		self.assertNotIn(OPERATOR, frappe.parse_json(suggestion.evidence)["users"])

		later = add_months(nowdate(), 7)
		check_sops(today=later)
		self.assertEqual(frappe.db.get_value(DOCTYPE, sop.name, "review_status"), "Review Overdue")
		self.assertTrue(
			frappe.db.exists(
				"Agent Suggestion",
				{"reference_name": sop.name, "rule_key": ("like", "sop-review:%"), "severity": "Warning"},
			)
		)
		with as_user(AUTHOR):
			record_review(sop.name, "Still right")
		self.assertFalse(
			frappe.db.exists(
				"Agent Suggestion",
				{"reference_name": sop.name, "rule_key": ("like", "sop-review:%"), "status": "Open"},
			)
		)
		self.assertEqual(
			getdate(frappe.db.get_value(DOCTYPE, sop.name, "next_review_on")),
			getdate(add_months(nowdate(), 6)),
		)
