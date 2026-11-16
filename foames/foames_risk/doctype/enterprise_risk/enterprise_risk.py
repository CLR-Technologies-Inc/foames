# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""One risk in the enterprise risk register.

On every save the record is checked and its derived values are filled in by the pure rules in
foames.foames_risk.risk: inherent and residual scores and ratings, the tolerance of its category,
whether the residual rating is within it, the strongest control in place, each control's next
verification date, each key risk indicator's breach flag and the next review date.

Management's acceptance of a residual risk above tolerance, and the periodic review, are recorded
only through the whitelisted methods below, so the record shows who accepted or reviewed what, and
when. An acceptance holds for the residual score it was given at: a change to that score clears it.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from foames.foames_risk import register
from foames.foames_risk.risk import assess, control_schedule, indicator_breached, next_due, review_interval

DOCTYPE = "Enterprise Risk"
ACCEPTANCE_FIELDS = ("accepted_by", "accepted_on", "accepted_score")
ACCEPT_ROLES = ("FoaMES Supervisor", "System Manager")


class EnterpriseRisk(Document):
	def validate(self):
		settings = register.settings()
		self.protect_system_fields()
		self.tolerance = register.category_tolerance(self.category, settings)
		self.risk_appetite = settings.get("risk_appetite")
		result = assess(self.as_rule_input(), settings)
		for message in result["warnings"]:
			frappe.msgprint(_(message), indicator="orange", alert=True)
		if result["errors"]:
			frappe.throw("<br>".join(_(e) for e in result["errors"]), title=_("Risk not valid"))
		for field in (
			"inherent_score",
			"inherent_rating",
			"residual_impact",
			"residual_likelihood",
			"residual_score",
			"residual_rating",
			"within_tolerance",
			"strongest_control",
			"controls_in_place",
			"target_score",
			"target_rating",
		):
			self.set(field, result.get(field))
		if not (self.target_impact or self.target_likelihood):
			self.target_score = self.target_rating = None
		if self.accepted_score and self.accepted_score != self.residual_score:
			for field in ACCEPTANCE_FIELDS:
				self.set(field, None)
		self.update_controls(settings)
		self.update_indicators()
		self.update_links()
		start = getdate(self.identified_on or nowdate())
		self.next_review_on = next_due(
			getdate(self.last_reviewed_on) if self.last_reviewed_on else None,
			start,
			review_interval(self.residual_rating, self.review_interval_days, settings),
		)
		if self.status == "Monitoring" and not (self.within_tolerance or self.accepted_by):
			frappe.throw(
				_(
					"A risk above its tolerance can be monitored only once management has accepted the residual "
					"risk. Treat it further or record the acceptance."
				)
			)
		if self.status == "Closed" and not (self.closure_note or "").strip():
			frappe.throw(_("Say why the risk is closed"))

	def protect_system_fields(self):
		"""Acceptance and review history are written only by the whitelisted methods."""
		if self.flags.recording:
			return
		before = self.get_doc_before_save()
		for field in (*ACCEPTANCE_FIELDS, "last_reviewed_on"):
			self.set(field, before.get(field) if before else None)
		if before:
			self.set("reviews", [row.as_dict() for row in before.get("reviews")])
		else:
			self.set("reviews", [])

	def as_rule_input(self) -> dict:
		return {
			"inherent_impact": self.inherent_impact,
			"inherent_likelihood": self.inherent_likelihood,
			"residual_impact": self.residual_impact or None,
			"residual_likelihood": self.residual_likelihood or None,
			"response": self.response,
			"transfer_to": self.transfer_to,
			"controls": [c.as_dict() for c in self.controls],
			"proposed_response": self.proposed_response,
			"target_impact": self.target_impact or None,
			"target_likelihood": self.target_likelihood or None,
			"tolerance": self.tolerance,
			"risk_statement": self.risk_statement,
		}

	def update_controls(self, settings: dict):
		before = self.get_doc_before_save()
		previous = {row.name: row for row in (before.get("controls") if before else [])}
		today = getdate(nowdate())
		for row in self.controls:
			old = previous.get(row.name)
			changed = not old or verification_of(old) != verification_of(row)
			if not changed:
				row.verified_by = old.verified_by
			elif row.verified_on or row.verification_result not in (None, "", "Not Verified"):
				row.verified_by = frappe.session.user
				if not row.verified_on:
					row.verified_on = today
			else:
				row.verified_by = None
			if row.verified_on and getdate(row.verified_on) > today:
				frappe.throw(_("Row {0}: a control cannot be verified in the future").format(row.idx))
			if row.evidence_name and not row.evidence_doctype:
				frappe.throw(_("Row {0}: choose the evidence type").format(row.idx))
			if row.evidence_doctype:
				register.check_linkable(row.evidence_doctype, _("Row {0} evidence").format(row.idx))
			schedule = control_schedule(
				{
					"status": row.status,
					"implemented_on": getdate(row.implemented_on) if row.implemented_on else None,
					"verified_on": getdate(row.verified_on) if row.verified_on else None,
					"verification_interval_days": row.verification_interval_days,
				},
				today,
				settings.get("verification_days"),
			)
			row.next_verification_on = schedule["next_verification_on"]

	def update_indicators(self):
		for row in self.indicators:
			row.breached = int(indicator_breached(row.current_value, row.threshold, row.direction or "Above"))

	def update_links(self):
		seen = set()
		for row in self.links:
			register.check_linkable(row.link_doctype, _("Linked record row {0}").format(row.idx))
			key = (row.link_doctype, row.link_name)
			if key in seen:
				frappe.throw(_("{0} {1} is linked twice").format(row.link_doctype, row.link_name))
			seen.add(key)
			row.source_rating = (
				register.source_rating(row.link_doctype, row.link_name) if row.relation == "Source" else None
			)


def verification_of(row) -> tuple:
	"""What a person records when they verify a control, comparable across saves."""
	return (
		str(getdate(row.get("verified_on"))) if row.get("verified_on") else None,
		row.get("verification_result") or "Not Verified",
		row.get("effectiveness") or "Not Assessed",
	)


def _load(name: str, ptype: str = "write"):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission(ptype)
	return doc


@frappe.whitelist(methods=["POST"])
def accept_residual_risk(name: str, justification: str) -> dict:
	"""Management accepts the residual risk at its current score. For a risk above its tolerance this
	is what lets it be monitored instead of treated further."""
	frappe.only_for(ACCEPT_ROLES)
	doc = _load(name)
	if not (justification or "").strip():
		frappe.throw(_("Say why the residual risk is accepted"))
	if doc.status == "Closed":
		frappe.throw(_("A closed risk is not accepted"))
	doc.acceptance_justification = justification.strip()
	doc.accepted_by = frappe.session.user
	doc.accepted_on = nowdate()
	doc.accepted_score = doc.residual_score
	doc.flags.recording = True
	doc.save()
	return {"accepted_by": doc.accepted_by, "accepted_on": str(doc.accepted_on), "score": doc.accepted_score}


@frappe.whitelist(methods=["POST"])
def record_review(name: str, notes: str | None = None) -> dict:
	"""The periodic review: the risk, its rating and its controls were looked at today. Adds a row to the
	review history and restarts the review interval."""
	doc = _load(name)
	if doc.status == "Closed":
		frappe.throw(_("A closed risk is not reviewed"))
	doc.flags.recording = True
	doc.last_reviewed_on = nowdate()
	doc.append(
		"reviews",
		{
			"reviewed_on": doc.last_reviewed_on,
			"reviewed_by": frappe.session.user,
			"residual_score": doc.residual_score,
			"residual_rating": doc.residual_rating,
			"within_tolerance": doc.within_tolerance,
			"notes": (notes or "").strip() or None,
		},
	)
	doc.save()
	return {"last_reviewed_on": str(doc.last_reviewed_on), "next_review_on": str(doc.next_review_on)}


@frappe.whitelist(methods=["POST"])
def create_from_template(template: str, title: str | None = None, machine: str | None = None) -> str:
	"""A new Identified risk with the template's statement, typical ratings and controls (as Planned).
	Returns its name."""
	frappe.has_permission(DOCTYPE, "create", throw=True)
	tpl = frappe.get_doc("Risk Template", template)
	tpl.check_permission("read")
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"title": title or tpl.title,
			"category": tpl.category,
			"objective": tpl.objective or "Operations",
			"risk_statement": tpl.risk_statement,
			"inherent_impact": tpl.inherent_impact or 3,
			"inherent_likelihood": tpl.inherent_likelihood or 3,
			"machine": machine,
			"template": tpl.name,
			"risk_owner": frappe.session.user,
			"controls": [
				{
					"control": c.control,
					"control_level": c.control_level,
					"control_function": c.control_function,
					"verification_method": c.verification_method,
					"status": "Planned",
				}
				for c in tpl.controls
			],
		}
	).insert()
	return doc.name


@frappe.whitelist(methods=["POST"])
def create_from_source(doctype: str, name: str) -> str:
	"""A new risk that summarises a detailed assessment (a hazard assessment, a PFMEA), linked to it as
	its Source. The detail and the controls stay on the source; its rating is watched from here.
	Returns the new risk's name."""
	frappe.has_permission(DOCTYPE, "create", throw=True)
	register.check_linkable(doctype, _("Source"))
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	values = register.source_values(doctype, name)
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"objective": "Operations",
			"risk_owner": frappe.session.user,
			**values,
			"links": [{"link_doctype": doctype, "link_name": name, "relation": "Source"}],
		}
	).insert()
	return doc.name


@frappe.whitelist()
def get_linkable_doctypes() -> list[str]:
	"""The record types a risk may link to on this site, for the form's pickers."""
	return register.linkable_doctypes()
