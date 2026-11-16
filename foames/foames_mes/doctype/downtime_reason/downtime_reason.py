# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

from frappe.model.document import Document


class DowntimeReason(Document):
	def validate(self):
		if not self.title:
			self.title = self.code
		if self.category in ("Planned", "Changeover"):
			self.counts_as_planned = 1
