# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A hazard with its risk before and after controls, on the 5 x 5 matrix, and the controls ranked on
the hierarchy of controls. Only controls marked In Place count towards the strongest control."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_ehs.ehs import assess_hazard, next_review


class HazardAssessment(Document):
	def validate(self):
		try:
			result = assess_hazard(
				self.likelihood,
				self.severity,
				self.residual_likelihood,
				self.residual_severity,
				[c.control_level for c in self.controls if c.in_place],
			)
		except ValueError as error:
			frappe.throw(_(str(error)[0].upper() + str(error)[1:]))
		self.risk_score = result["risk_score"]
		self.risk_level = result["risk_level"]
		self.residual_score = result["residual_score"]
		self.residual_level = result["residual_level"]
		self.strongest_control = result["strongest_control"]
		if self.review_interval_days is not None and int(self.review_interval_days) < 0:
			frappe.throw(_("The review interval cannot be negative"))
		self.next_review_on = next_review(
			frappe.utils.getdate(self.reviewed_on) if self.reviewed_on else None, self.review_interval_days
		)

	def weaknesses(self) -> list[str]:
		return assess_hazard(
			self.likelihood,
			self.severity,
			self.residual_likelihood,
			self.residual_severity,
			[c.control_level for c in self.controls if c.in_place],
		)["weaknesses"]
