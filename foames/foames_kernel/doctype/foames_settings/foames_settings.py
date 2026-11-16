# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters import get_adapters


class FoaMESSettings(Document):
	def validate(self):
		if self.default_erp_system and self.default_erp_system not in get_adapters():
			frappe.throw(_("{0} is not a registered ERP system").format(frappe.bold(self.default_erp_system)))
