# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""An NPI program run through stage gates.

A new program gets one gate per stage and the deliverable template for its product type. The
current stage and status move only through `record_gate_decision`, which a reviewer other than the
program lead calls; the rules are in foames.foames_life_sciences.npi. The decision fields of a gate
cannot be edited by hand, and the version history (track changes) keeps every decision.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from foames.foames_life_sciences import npi

DECIDERS = ("FoaMES Quality", "FoaMES Supervisor", "System Manager")
GATE_SYSTEM_FIELDS = (
	"decision",
	"decided_by",
	"decided_on",
	"conditions",
	"conditions_due",
	"conditions_closed",
	"closed_by",
	"closed_on",
)


class NPIProgram(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if self.is_new():
			self.current_stage = npi.STAGES[0]
			self.status = "Active"
			if not self.deliverables:
				for stage, name, required in npi.template_for(self.product_type):
					self.append(
						"deliverables", {"stage": stage, "deliverable": name, "required": int(required)}
					)
			for gate in self.gates:
				self.clear_decision(gate)
		elif not self.flags.gate_decision:
			if (self.current_stage, self.status) != (before.current_stage, before.status):
				frappe.throw(_("Stage and status change only through a gate decision"))
			self.check_gate_fields(before)
		self.ensure_gates()
		for row in self.deliverables:
			if row.document_name and not row.document_type:
				frappe.throw(_("Deliverable {0} names a document without its type").format(row.idx))

	def clear_decision(self, gate):
		for field in GATE_SYSTEM_FIELDS:
			gate.set(field, None)

	def ensure_gates(self):
		present = {g.stage for g in self.gates}
		if len(present) != len(self.gates):
			frappe.throw(_("Each stage has one gate"))
		for stage in npi.STAGES:
			if stage not in present:
				self.append("gates", {"stage": stage})
		self.gates.sort(key=lambda g: npi.stage_index(g.stage))
		for i, gate in enumerate(self.gates, start=1):
			gate.idx = i

	def check_gate_fields(self, before):
		old = {g.stage: g for g in before.gates}
		for gate in self.gates:
			previous = old.get(gate.stage)
			for field in GATE_SYSTEM_FIELDS:
				new_value = gate.get(field) or None
				old_value = (previous.get(field) or None) if previous else None
				if str(new_value or "") != str(old_value or ""):
					frappe.throw(
						_("The {0} gate's decision fields change only through Record Gate Decision").format(
							_(gate.stage)
						)
					)

	def gate(self, stage):
		return next(g for g in self.gates if g.stage == stage)

	def deliverable_rows(self):
		return [
			{"stage": d.stage, "deliverable": d.deliverable, "required": d.required, "status": d.status}
			for d in self.deliverables
		]

	@frappe.whitelist()
	def record_gate_decision(self, decision, conditions=None, conditions_due=None):
		"""Record a gate decision on the current stage and move the program accordingly."""
		self.check_permission("write")
		if not set(DECIDERS) & set(frappe.get_roles()):
			frappe.throw(
				_("Gate decisions are recorded by FoaMES Quality or FoaMES Supervisor"),
				frappe.PermissionError,
			)
		due = getdate(conditions_due) if conditions_due else None
		problems = npi.decision_problems(
			program_status=self.status,
			current_stage=self.current_stage,
			gate_stage=self.current_stage,
			decision=decision,
			deliverables=self.deliverable_rows(),
			conditions=conditions,
			conditions_due=due,
			decided_by=frappe.session.user,
			program_lead=self.program_lead,
		)
		if problems:
			frappe.throw("<br>".join(problems), title=_("Gate decision refused"))
		gate = self.gate(self.current_stage)
		gate.update(
			{
				"decision": decision,
				"decided_by": frappe.session.user,
				"decided_on": now_datetime(),
				"conditions": conditions,
				"conditions_due": due,
				"conditions_closed": 0,
				"closed_by": None,
				"closed_on": None,
			}
		)
		self.current_stage, self.status = npi.apply_decision(self.current_stage, decision)
		self.save_decision()
		return {"current_stage": self.current_stage, "status": self.status}

	@frappe.whitelist()
	def close_gate_conditions(self, stage):
		"""Mark the conditions of a Conditional Go as met."""
		self.check_permission("write")
		if not set(DECIDERS) & set(frappe.get_roles()):
			frappe.throw(
				_("Gate conditions are closed by FoaMES Quality or FoaMES Supervisor"), frappe.PermissionError
			)
		gate = self.gate(stage)
		if gate.decision != "Conditional Go" or gate.conditions_closed:
			frappe.throw(_("The {0} gate has no open conditions").format(_(stage)))
		gate.update({"conditions_closed": 1, "closed_by": frappe.session.user, "closed_on": now_datetime()})
		self.save_decision()

	def save_decision(self):
		self.flags.gate_decision = True
		try:
			self.save()
		finally:
			self.flags.gate_decision = False

	@frappe.whitelist()
	def get_stage_progress(self):
		rows = self.deliverable_rows()
		return [npi.stage_progress(rows, stage) for stage in npi.STAGES]
