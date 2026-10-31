# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters.erpnext import erpnext_installed


class ERPNextAdapterSettings(Document):
	def validate(self):
		if self.enable_postings and not erpnext_installed():
			frappe.throw(_("ERPNext is not installed on this site, so postings cannot be enabled"))
		if (self.floor_lookahead_days or 0) < 0:
			self.floor_lookahead_days = 0
