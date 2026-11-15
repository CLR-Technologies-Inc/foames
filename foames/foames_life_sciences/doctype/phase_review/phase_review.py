# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A formal phase review of one NPI gate (the Phase Review Discipline).

Opened against a program, it takes the program's current stage, its board and the board's
members as attendees. People mark attendance, votes, minutes and actions. Submitting closes the
review with the Chair's decision: it is refused unless the Chair submits it, a quorum of voting
members was present and voted, the stage's entry criteria are met and, for Go or Conditional Go,
its exit criteria and required deliverables are done. The decision is then recorded on the
program's gate with a link to this review, and the program moves. After submission only the
action items change. The rules are in foames.foames_life_sciences.phase_review and npi.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

from foames.foames_life_sciences import phase_review


class PhaseReview(Document):
	def validate(self):
		program = frappe.get_doc("NPI Program", self.npi_program)
		if self.is_new():
			if program.status in ("Launched", "Cancelled"):
				frappe.throw(
					_("{0} is {1}; it has no further phase reviews").format(program.name, program.status)
				)
			if not program.phase_review_board:
				frappe.throw(_("{0} has no phase review board").format(program.name))
			self.stage = program.current_stage
			self.phase_review_board = program.phase_review_board
			self.review_type = self.review_type or phase_review.REVIEW_TYPE_FOR_STAGE[self.stage]
			if not self.attendees:
				board = frappe.get_doc("Phase Review Board", self.phase_review_board)
				for m in board.members:
					self.append(
						"attendees", {"user": m.user, "board_role": m.board_role, "function": m.function}
					)
		board = frappe.get_doc("Phase Review Board", self.phase_review_board)
		self.chair = board.chair
		members = {m.user: m.board_role for m in board.members}
		for a in self.attendees:
			a.board_role = members.get(a.user, "Guest")
			if a.board_role not in phase_review.VOTING_ROLES and a.vote:
				frappe.throw(_("{0} is not a voting member of the board").format(a.user))
		counts = self.tally()["counts"]
		self.vote_summary = ", ".join(f"{v}: {n}" for v, n in sorted(counts.items())) or None

	def tally(self):
		return phase_review.tally(self.attendee_rows())

	def attendee_rows(self):
		return [
			{"user": a.user, "board_role": a.board_role, "present": a.present, "vote": a.vote}
			for a in self.attendees
		]

	def before_submit(self):
		program = frappe.get_doc("NPI Program", self.npi_program)
		if program.current_stage != self.stage:
			frappe.throw(
				_("The program has moved on from {0} since this review was opened").format(self.stage)
			)
		board = frappe.get_doc("Phase Review Board", self.phase_review_board)
		problems = phase_review.review_problems(
			stage=self.stage,
			decision=self.decision,
			attendees=self.attendee_rows(),
			quorum=cint(board.quorum),
			criteria=program.criteria_rows(),
			decided_by=frappe.session.user,
			rationale=self.rationale,
		)
		if problems:
			frappe.throw("<br>".join(problems), title=_("The phase review cannot be closed"))
		self.criteria_at_review = "\n".join(
			f"[{'x' if c['met'] else ' '}] {c['kind']}: {c['criterion']}"
			for c in program.criteria_rows()
			if c["stage"] == self.stage
		)

	def on_submit(self):
		program = frappe.get_doc("NPI Program", self.npi_program)
		program.record_gate_decision(
			self.decision,
			self.rationale,
			getdate(self.conditions_due) if self.conditions_due else None,
			phase_review=self.name,
		)
