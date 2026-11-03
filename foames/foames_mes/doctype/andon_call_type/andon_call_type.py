# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_mes.andon import DEFAULT_CALL_TYPES


class AndonCallType(Document):
	def validate(self):
		if not self.title:
			self.title = self.code
		for field in ("acknowledge_within_minutes", "resolve_within_minutes"):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(self.meta.get_label(field)))


def create_default_call_types():
	"""The standard call types, created once on install and by a patch; edit or disable them freely."""
	for values in DEFAULT_CALL_TYPES:
		if not frappe.db.exists("Andon Call Type", values["code"]):
			frappe.get_doc({"doctype": "Andon Call Type", **values}).insert(ignore_permissions=True)
