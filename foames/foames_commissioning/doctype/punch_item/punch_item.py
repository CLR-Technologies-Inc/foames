# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A deficiency found during commissioning.

Category A must be cleared before start-up and handover and can never be deferred. Category B must be
cleared before handover unless it is deferred with an owner and a due date. Category C never blocks.
Closing an item needs the action taken and records who verified it. Punch items may be raised on a
package after handover; they then follow the equipment into operation.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_commissioning.commissioning import punch_deferral_problem
from foames.foames_commissioning.doctype.commissioning_package.commissioning_package import (
	check_tag_in_scope,
	refresh_package,
)


class PunchItem(Document):
	def before_insert(self):
		self.raised_by = self.raised_by or frappe.session.user
		self.raised_on = self.raised_on or now_datetime()

	def validate(self):
		if frappe.db.get_value("Commissioning Package", self.package, "status") == "Cancelled":
			frappe.throw(_("Package {0} is cancelled").format(self.package))
		check_tag_in_scope(self.package, self.equipment_tag)
		problem = punch_deferral_problem(self.category, self.deferred, self.assigned_to, self.due_on)
		if problem:
			frappe.throw(_(problem))
		before = self.get_doc_before_save()
		if before and before.status in ("Closed", "Cancelled") and self.status != before.status:
			frappe.throw(
				_("A {0} punch item cannot be reopened; raise a new one").format(_(before.status).lower())
			)
		if self.status == "Closed":
			if not (self.action_taken or "").strip():
				frappe.throw(_("Record the action taken before closing the punch item"))
			self.verified_by = self.verified_by or frappe.session.user
			self.closed_on = self.closed_on or now_datetime()
		else:
			self.verified_by = None
			self.closed_on = None

	def on_update(self):
		if self.status in ("Closed", "Cancelled"):
			self.resolve_suggestions()
		refresh_package(self.package)

	def after_delete(self):
		refresh_package(self.package)

	def resolve_suggestions(self):
		for name in frappe.get_all(
			"Agent Suggestion",
			filters={"reference_doctype": self.doctype, "reference_name": self.name, "status": "Open"},
			pluck="name",
		):
			suggestion = frappe.get_doc("Agent Suggestion", name)
			suggestion.status = "Done"
			suggestion.resolution = _("Punch item {0} is {1}").format(self.name, _(self.status).lower())
			suggestion.save(ignore_permissions=True)
