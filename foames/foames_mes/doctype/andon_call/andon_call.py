# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A request for help at a machine, and how quickly it was answered.

The status moves Open -> Acknowledged -> Resolved (or straight to Resolved, or to Cancelled), and
the time and user of each step are stamped when it happens, whether through the API or the form.
Escalation of calls that miss their call type's targets is in foames.foames_mes.andon.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes.andon import FINAL_STATUSES, OPEN_STATUSES, allowed_transition, minutes_between


class AndonCall(Document):
	def validate(self):
		before = self.get_doc_before_save()
		previous = before.status if before else None
		if not allowed_transition(previous, self.status):
			frappe.throw(_("An Andon Call cannot go from {0} to {1}").format(_(previous), _(self.status)))
		if self.is_new():
			self.raised_at = self.raised_at or now_datetime()
			self.raised_by = self.raised_by or frappe.session.user
			if frappe.db.get_value("Andon Call Type", self.call_type, "disabled"):
				frappe.throw(_("Call type {0} is disabled").format(self.call_type))
		now = now_datetime()
		if self.status == "Acknowledged" and not self.acknowledged_at:
			self.acknowledged_at, self.acknowledged_by = now, frappe.session.user
		if self.status in FINAL_STATUSES and not self.resolved_at:
			self.resolved_at, self.resolved_by = now, frappe.session.user
		raised = get_datetime(self.raised_at)
		answered = self.acknowledged_at or (self.resolved_at if self.status == "Resolved" else None)
		self.response_minutes = minutes_between(raised, get_datetime(answered) if answered else None)
		self.resolution_minutes = minutes_between(
			raised, get_datetime(self.resolved_at) if self.resolved_at else None
		)

	def on_update(self):
		if self.status != "Open":
			close_escalations(self.name, ("acknowledge",) if self.status == "Acknowledged" else None)


def close_escalations(call: str, stages=None):
	"""Mark the open escalation suggestions of a call Done once the call has moved on."""
	for stage in stages or ("acknowledge", "resolve"):
		name = frappe.db.get_value(
			"Agent Suggestion", {"rule_key": f"andon:{call}:{stage}", "status": "Open"}, "name"
		)
		if name:
			doc = frappe.get_doc("Agent Suggestion", name)
			doc.status = "Done"
			doc.resolution = _("Andon call {0} is now {1}").format(
				call, _(frappe.db.get_value("Andon Call", call, "status"))
			)
			doc.save(ignore_permissions=True)


def open_andon_calls(now=None, machine: str | None = None) -> list[dict]:
	"""Open and acknowledged calls with their call type's targets and minutes open, oldest first, for
	the floor snapshot and the escalation rule."""
	now = now or now_datetime()
	call, kind = frappe.qb.DocType("Andon Call"), frappe.qb.DocType("Andon Call Type")
	query = (
		frappe.qb.from_(call)
		.left_join(kind)
		.on(kind.name == call.call_type)
		.select(
			call.name,
			call.machine,
			call.call_type,
			call.status,
			call.note,
			call.raised_at,
			call.raised_by,
			call.acknowledged_at,
			call.ack_escalated,
			call.resolve_escalated,
			kind.acknowledge_within_minutes,
			kind.resolve_within_minutes,
			kind.escalation_severity,
		)
		.where(call.status.isin(list(OPEN_STATUSES)))
		.orderby(call.raised_at)
	)
	if machine:
		query = query.where(call.machine == machine)
	rows = query.run(as_dict=True)
	for r in rows:
		r["minutes_open"] = minutes_between(get_datetime(r.raised_at), now)
	return rows


def _call_for_update(name: str):
	doc = frappe.get_doc("Andon Call", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist(methods=["POST"])
def raise_andon(machine: str, call_type: str, note: str | None = None) -> dict:
	"""Raise a call for help at a machine. Returns the new call's name and status."""
	frappe.has_permission("Andon Call", "create", throw=True)
	doc = frappe.get_doc(
		{"doctype": "Andon Call", "machine": machine, "call_type": call_type, "note": note}
	).insert()
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def acknowledge_andon(name: str) -> dict:
	"""Someone is on the way: the call becomes Acknowledged and its response time is fixed."""
	doc = _call_for_update(name)
	if doc.status == "Open":
		doc.status = "Acknowledged"
		doc.save()
	return {"name": doc.name, "status": doc.status, "response_minutes": doc.response_minutes}


@frappe.whitelist(methods=["POST"])
def resolve_andon(name: str, resolution: str | None = None, cancel: bool = False) -> dict:
	"""Close a call: Resolved with what was done, or Cancelled when help is no longer needed."""
	doc = _call_for_update(name)
	if doc.status not in FINAL_STATUSES:
		doc.status = "Cancelled" if frappe.utils.cint(cancel) else "Resolved"
		if resolution:
			doc.resolution = resolution
		doc.save()
	return {"name": doc.name, "status": doc.status, "resolution_minutes": doc.resolution_minutes}


@frappe.whitelist()
def list_open_andon_calls(machine: str | None = None) -> list[dict]:
	"""Open and acknowledged calls, oldest first, with minutes open and their targets."""
	frappe.has_permission("Andon Call", "read", throw=True)
	return open_andon_calls(machine=machine)


def escalate_andon_calls() -> list[str]:
	"""Scheduled every five minutes: raise a suggestion for each call that has just missed a target,
	and flag the call so the same target is not raised again (even if the suggestion is dismissed)."""
	from foames.foames_mes.andon import overdue_andon_calls
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	findings = overdue_andon_calls({"andon_calls": open_andon_calls()})
	created = raise_suggestions(findings)
	for finding in findings:
		call, stage = finding["reference_name"], finding["rule_key"].rsplit(":", 1)[1]
		frappe.db.set_value(
			"Andon Call",
			call,
			"ack_escalated" if stage == "acknowledge" else "resolve_escalated",
			1,
			update_modified=False,
		)
	return created
