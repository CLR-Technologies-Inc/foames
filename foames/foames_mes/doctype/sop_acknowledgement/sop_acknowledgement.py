# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A person's record that they read, or were trained on, one SOP revision.

Records are made through the SOP's Acknowledge and Record Training actions. One record per person
and revision; the SOP code and revision are copied on so that the training matrix can tell an
acknowledgement of an earlier revision (Outdated) from none at all (Missing).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class SOPAcknowledgement(Document):
	def validate(self):
		sop = frappe.db.get_value(
			"Standard Operating Procedure", self.sop, ["sop_code", "revision"], as_dict=True
		)
		if not sop:
			frappe.throw(_("SOP {0} not found").format(self.sop))
		self.sop_code, self.revision = sop.sop_code, sop.revision
		if self.is_new():
			self.acknowledged_on = self.acknowledged_on or now_datetime()
			if frappe.db.exists("SOP Acknowledgement", {"sop": self.sop, "user": self.user}):
				frappe.throw(_("{0} has already acknowledged {1}").format(self.user, self.sop))
		else:
			before = self.get_doc_before_save()
			if before and (before.sop != self.sop or before.user != self.user):
				frappe.throw(_("An acknowledgement cannot be moved to another SOP or person"))
