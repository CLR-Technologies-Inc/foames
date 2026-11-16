# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A phase review board: the cross-functional group that holds decision authority over the gates
of the NPI programs assigned to it. The rules are in foames.foames_life_sciences.phase_review."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from foames.foames_life_sciences import phase_review


class PhaseReviewBoard(Document):
	def autoname(self):
		self.name = (self.board_name or "").strip()

	def validate(self):
		problems = phase_review.board_problems(
			[{"user": m.user, "board_role": m.board_role} for m in self.members], cint(self.quorum)
		)
		if problems:
			frappe.throw("<br>".join(problems), title=_("The board is not complete"))
		self.chair = next(m.user for m in self.members if m.board_role == "Chair")
