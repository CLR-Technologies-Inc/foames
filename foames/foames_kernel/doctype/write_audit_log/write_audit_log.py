# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document


class WriteAuditLog(Document):
	"""One entry of the append-only, hash-chained log of everything the write gate did."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Audit entries cannot be changed"))
		if not self.flags.foames_audit:
			frappe.throw(_("Audit entries are written by the write gate only"))

	def on_trash(self):
		frappe.throw(_("Audit entries cannot be deleted"))
