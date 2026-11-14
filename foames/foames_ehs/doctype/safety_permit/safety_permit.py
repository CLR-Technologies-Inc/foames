# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A permit to work.

A permit is Draft while it is prepared, Active while the work may go on, Suspended when the work is
stopped for a while (an alarm, a shift change), and ends Closed, Cancelled or Expired. An ended
permit is never reopened: the next piece of work gets a new one. Activating a lockout, confined
space, line break or electrical permit needs every isolation point locked and verified at zero
energy; closing needs every lock removed. The rules are in foames.foames_ehs.ehs.permit_problems.

FoaMES records the permit and watches the machine; it never isolates or starts anything itself.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from foames.foames_ehs.ehs import DEFAULT_MAX_PERMIT_HOURS, permit_problems

ENDED = ("Closed", "Cancelled", "Expired")


class SafetyPermit(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if before and before.status in ENDED and self.status != before.status:
			frappe.throw(
				_("A {0} permit cannot be reopened; raise a new one").format(_(before.status).lower())
			)
		user = frappe.session.user
		for p in self.isolation_points:
			if p.lock_id and not p.locked_by:
				p.locked_by = user
			if p.verified and not p.verified_by:
				p.verified_by = user
			if not p.verified:
				p.verified_by = None
			if p.removed_on and not p.removed_by:
				p.removed_by = user
			if p.removed_on and get_datetime(p.removed_on) > now_datetime():
				frappe.throw(_("Row {0}: a lock cannot be removed in the future").format(p.idx))
		if self.status == "Active" and not self.issued_by:
			self.issued_by = user
		problems = permit_problems(self.as_rule_dict(), DEFAULT_MAX_PERMIT_HOURS)
		if problems:
			frappe.throw("<br>".join(_(p[0].upper() + p[1:]) for p in problems), title=_("Permit not valid"))
		if self.status == "Active" and not self.activated_on:
			self.activated_on = now_datetime()
		if self.status == "Closed" and not self.closed_on:
			self.closed_on = now_datetime()
			self.closed_by = user

	def as_rule_dict(self) -> dict:
		return {
			"name": self.name,
			"permit_type": self.permit_type,
			"status": self.status,
			"machine": self.machine,
			"valid_from": get_datetime(self.valid_from) if self.valid_from else None,
			"valid_to": get_datetime(self.valid_to) if self.valid_to else None,
			"issued_by": self.issued_by,
			"performed_by": self.performed_by,
			"isolation_points": [
				{
					"isolation_point": p.isolation_point,
					"lock_id": p.lock_id,
					"verified": p.verified,
					"removed_on": p.removed_on,
				}
				for p in self.isolation_points
			],
		}

	def on_update(self):
		if self.status in ENDED:
			for name in frappe.get_all(
				"Agent Suggestion",
				filters={
					"reference_doctype": "Safety Permit",
					"reference_name": self.name,
					"status": "Open",
					"category": "Safety",
				},
				pluck="name",
			):
				# An expired permit's own warning stays open until someone deals with it.
				if self.status == "Expired":
					continue
				suggestion = frappe.get_doc("Agent Suggestion", name)
				suggestion.status = "Done"
				suggestion.resolution = _("Permit {0} {1}").format(self.name, _(self.status).lower())
				suggestion.save(ignore_permissions=True)


def active_permits(machines: list[str] | None = None) -> list[dict]:
	"""Active and suspended permits with their isolation points, as rule dicts."""
	filters = {"status": ("in", ("Active", "Suspended"))}
	if machines is not None:
		if not machines:
			return []
		filters["machine"] = ("in", machines)
	return [
		frappe.get_doc("Safety Permit", name).as_rule_dict()
		for name in frappe.get_all("Safety Permit", filters=filters, pluck="name", order_by="name")
	]
