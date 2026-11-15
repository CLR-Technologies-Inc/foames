# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""SOP document control rules: lifecycle, sign-off, review dates, training status. No Frappe site needed."""

import unittest
from datetime import date, datetime
from itertools import pairwise

from foames.foames_mes.sop import (
	STATUSES,
	acknowledgement_status,
	add_months,
	allowed_transition,
	applies,
	approvals_complete,
	findings,
	missing_approvals,
	next_review,
	next_revision,
	normalise_code,
	review_rule_key,
	review_status,
	revision_name,
	signable_rows,
	training_due,
	training_matrix,
	training_rule_key,
)


class TestLifecycle(unittest.TestCase):
	def test_forward_path(self):
		path = [None, "Draft", "In Review", "Approved", "Effective", "Superseded"]
		for previous, new in pairwise(path):
			self.assertTrue(allowed_transition(previous, new), (previous, new))

	def test_rejection_and_retirement(self):
		self.assertTrue(allowed_transition("In Review", "Draft"))
		self.assertTrue(allowed_transition("Draft", "Obsolete"))
		self.assertTrue(allowed_transition("Approved", "Obsolete"))
		self.assertTrue(allowed_transition("Effective", "Obsolete"))

	def test_no_shortcuts_or_resurrection(self):
		self.assertFalse(allowed_transition("Draft", "Approved"))
		self.assertFalse(allowed_transition("Draft", "Effective"))
		self.assertFalse(allowed_transition("In Review", "Effective"))
		self.assertFalse(allowed_transition("Effective", "Draft"))
		self.assertFalse(allowed_transition(None, "Effective"))
		for final in ("Superseded", "Obsolete"):
			for status in STATUSES:
				if status != final:
					self.assertFalse(allowed_transition(final, status), (final, status))

	def test_staying_put_is_allowed(self):
		for status in STATUSES:
			self.assertTrue(allowed_transition(status, status))


class TestNaming(unittest.TestCase):
	def test_normalise_code(self):
		self.assertEqual(normalise_code("  sop-qa-001 "), "SOP-QA-001")
		self.assertEqual(normalise_code("press  line 4"), "PRESS-LINE-4")
		self.assertEqual(normalise_code("QA/7.5_a"), "QA/7.5_A")

	def test_bad_codes(self):
		for code in ("", None, "   ", "-LEADING", "SOP#1", "SOP:1"):
			with self.assertRaises(ValueError):
				normalise_code(code)

	def test_revisions(self):
		self.assertEqual(revision_name("SOP-QA-001", 3), "SOP-QA-001-R3")
		self.assertEqual(next_revision([]), 1)
		self.assertEqual(next_revision([1, 3, 2]), 4)
		self.assertEqual(next_revision([None, 0]), 1)


class TestSignOff(unittest.TestCase):
	def rows(self):
		return [
			{"role": "FoaMES Supervisor", "signed_by": None},
			{"role": "FoaMES Quality", "signed_by": None},
		]

	def test_role_holder_signs_matching_row(self):
		self.assertEqual(signable_rows(self.rows(), "q@x", {"FoaMES Quality"}, "author@x"), [1])
		self.assertEqual(
			signable_rows(self.rows(), "both@x", {"FoaMES Quality", "FoaMES Supervisor"}, "author@x"), [0, 1]
		)

	def test_author_cannot_sign(self):
		self.assertEqual(signable_rows(self.rows(), "author@x", {"FoaMES Quality"}, "author@x"), [])

	def test_one_signature_per_person(self):
		rows = self.rows()
		rows[0]["signed_by"] = "both@x"
		self.assertEqual(signable_rows(rows, "both@x", {"FoaMES Quality", "FoaMES Supervisor"}, "a@x"), [])

	def test_without_the_role(self):
		self.assertEqual(signable_rows(self.rows(), "op@x", {"FoaMES Operator"}, "a@x"), [])

	def test_completeness(self):
		rows = self.rows()
		self.assertFalse(approvals_complete(rows))
		self.assertEqual(missing_approvals(rows), ["FoaMES Supervisor", "FoaMES Quality"])
		rows[0]["signed_by"], rows[1]["signed_by"] = "s@x", "q@x"
		self.assertTrue(approvals_complete(rows))
		self.assertEqual(missing_approvals(rows), [])
		self.assertFalse(approvals_complete([]))


class TestReview(unittest.TestCase):
	def test_add_months_clamps(self):
		self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
		self.assertEqual(add_months(date(2028, 1, 31), 1), date(2028, 2, 29))
		self.assertEqual(add_months(date(2026, 11, 14), 12), date(2027, 11, 14))
		self.assertEqual(add_months(date(2026, 11, 30), 3), date(2027, 2, 28))

	def test_next_review(self):
		self.assertEqual(next_review(date(2026, 1, 15), 12), date(2027, 1, 15))
		self.assertEqual(next_review("2026-01-15", 6, "2026-05-01"), date(2026, 11, 1))
		self.assertEqual(next_review(datetime(2026, 1, 15, 9, 0), 12), date(2027, 1, 15))
		self.assertIsNone(next_review(date(2026, 1, 15), 0))
		self.assertIsNone(next_review(None, 12))

	def test_review_bands(self):
		due = date(2026, 12, 31)
		self.assertEqual(review_status(due, date(2026, 11, 1)), "Current")
		self.assertEqual(review_status(due, date(2026, 12, 1)), "Review Due Soon")
		self.assertEqual(review_status(due, date(2026, 12, 31)), "Review Due Soon")
		self.assertEqual(review_status(due, date(2027, 1, 1)), "Review Overdue")
		self.assertEqual(review_status(None, date(2027, 1, 1)), "Current")


class TestTraining(unittest.TestCase):
	def test_status(self):
		self.assertEqual(acknowledgement_status(None, 2), "Missing")
		self.assertEqual(acknowledgement_status(1, 2), "Outdated")
		self.assertEqual(acknowledgement_status(2, 2), "Current")
		self.assertEqual(acknowledgement_status(3, 2), "Current")

	def test_matrix(self):
		self.assertEqual(
			training_matrix({"b@x", "a@x", "c@x"}, {"a@x": 2, "b@x": 1}, 2),
			{"a@x": "Current", "b@x": "Outdated", "c@x": "Missing"},
		)

	def test_training_due(self):
		self.assertFalse(training_due(date(2026, 11, 1), 14, date(2026, 11, 15)))
		self.assertTrue(training_due(date(2026, 11, 1), 14, date(2026, 11, 16)))
		self.assertTrue(training_due(date(2026, 11, 1), 0, date(2026, 11, 2)))
		self.assertFalse(training_due(None, 14, date(2026, 11, 16)))


class TestApplicability(unittest.TestCase):
	def test_site_wide(self):
		self.assertTrue(applies([], "PRESS-1", "L1"))

	def test_machine_and_line(self):
		rows = [{"machine": "PRESS-1"}, {"line": "L2"}]
		self.assertTrue(applies(rows, "PRESS-1", "L9"))
		self.assertTrue(applies(rows, "PRESS-7", "L2"))
		self.assertFalse(applies(rows, "PRESS-7", "L9"))
		self.assertFalse(applies(rows, None, None))

	def test_machine_row_does_not_cover_its_line(self):
		self.assertFalse(applies([{"machine": "PRESS-1", "line": "L1"}], "PRESS-2", "L1"))

	def test_process_reference_only_covers_no_machine(self):
		self.assertFalse(applies([{"external_reference": "ER-0001"}], "PRESS-1", "L1"))


class TestFindings(unittest.TestCase):
	def sop(self, **overrides):
		values = {
			"name": "SOP-PRS-004-R2",
			"code": "SOP-PRS-004",
			"title": "Die change",
			"revision": 2,
			"review_status": "Current",
			"next_review_on": date(2027, 1, 1),
			"overdue_users": [],
			"acknowledge_days": 14,
		}
		values.update(overrides)
		return values

	def test_nothing_to_raise(self):
		self.assertEqual(findings([self.sop()]), [])

	def test_review_findings(self):
		soon = findings([self.sop(review_status="Review Due Soon")])
		self.assertEqual(len(soon), 1)
		self.assertEqual(soon[0]["severity"], "Info")
		self.assertEqual(soon[0]["category"], "Quality")
		self.assertEqual(soon[0]["reference_doctype"], "Standard Operating Procedure")
		self.assertEqual(
			soon[0]["rule_key"], review_rule_key("SOP-PRS-004-R2", date(2027, 1, 1), "Review Due Soon")
		)
		overdue = findings([self.sop(review_status="Review Overdue")])
		self.assertEqual(overdue[0]["severity"], "Warning")
		self.assertNotEqual(overdue[0]["rule_key"], soon[0]["rule_key"])

	def test_training_finding(self):
		users = [f"u{i:02d}@x" for i in range(12)]
		out = findings([self.sop(overdue_users=users)])
		self.assertEqual(len(out), 1)
		self.assertEqual(out[0]["rule_key"], training_rule_key("SOP-PRS-004-R2"))
		self.assertIn("12 people", out[0]["title"])
		self.assertIn("and 2 more", out[0]["suggestion"])
		self.assertEqual(out[0]["evidence"]["users"], users)


if __name__ == "__main__":
	unittest.main()
