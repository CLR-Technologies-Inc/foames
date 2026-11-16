# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_risk.risk import check_rating


class RiskTemplate(Document):
	def validate(self):
		for field in ("inherent_impact", "inherent_likelihood"):
			if self.get(field):
				try:
					check_rating(self.get(field), self.meta.get_label(field))
				except ValueError as e:
					frappe.throw(_(str(e)))
