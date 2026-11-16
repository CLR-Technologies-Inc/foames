# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

from frappe.model.document import Document


class RiskCategory(Document):
	def validate(self):
		self.category_name = (self.category_name or "").strip()
