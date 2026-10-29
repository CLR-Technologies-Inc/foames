# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters import get_adapters


class FoaMESSettings(Document):
	def validate(self):
		if self.default_erp_system and self.default_erp_system not in get_adapters():
			frappe.throw(_("{0} is not a registered ERP system").format(frappe.bold(self.default_erp_system)))
