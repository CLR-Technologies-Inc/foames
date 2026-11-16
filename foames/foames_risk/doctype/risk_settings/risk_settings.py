# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_risk.risk import RATINGS, normalise_bands


class RiskSettings(Document):
	def validate(self):
		try:
			bands = normalise_bands(
				{
					"Very Low": self.very_low_max,
					"Low": self.low_max,
					"Moderate": self.moderate_max,
					"High": self.high_max,
				}
			)
		except ValueError as e:
			frappe.throw(_(str(e)))
		self.very_low_max, self.low_max, self.moderate_max, self.high_max = (bands[r] for r in RATINGS[:-1])
		for field in ("review_days", "high_risk_review_days", "verification_days"):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(_(self.meta.get_label(field))))
