# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One revision of a work instruction: the steps an operator follows at a station.

A revision is edited as a Draft, Released for use on the floor, and made Obsolete when a later
revision of the same code is released. A released or obsolete revision cannot be edited: a change is
a new revision (`new_revision`), so every run points at exactly the steps the operator saw. Only
FoaMES Engineers, FoaMES Quality and System Managers release a revision. The pure rules are in
foames.foames_mes.work_instructions.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from foames.foames_mes.work_instructions import (
	allowed_template_transition,
	estimated_minutes,
	validate_template_step,
)

RELEASE_ROLES = ("FoaMES Engineer", "FoaMES Quality", "System Manager")

# Fields of a step that define it; a released revision may not change any of them.
STEP_FIELDS = (
	"title",
	"capture",
	"optional",
	"estimated_minutes",
	"sign_off_role",
	"stop_on_fail",
	"instruction",
	"image",
	"attachment",
	"video_url",
	"unit",
	"has_lower_limit",
	"lower_limit",
	"target_value",
	"has_upper_limit",
	"upper_limit",
	"choices",
	"failing_choices",
	"post_measurement",
	"measurement_name",
)
HEADER_FIELDS = (
	"title",
	"operation",
	"machine",
	"machine_type",
	"item_reference",
	"governing_sop",
	"description",
	"safety_notes",
)


def next_revision(code: str) -> int:
	highest = frappe.db.get_value(
		"Work Instruction", {"instruction_code": code}, "revision", order_by="revision desc"
	)
	return cint(highest) + 1


class WorkInstruction(Document):
	def autoname(self):
		self.instruction_code = (self.instruction_code or "").strip()
		if not self.instruction_code:
			frappe.throw(_("Instruction Code is required"))
		if not self.revision:
			self.revision = next_revision(self.instruction_code)
		self.name = f"{self.instruction_code}-REV{cint(self.revision):02d}"

	def validate(self):
		before = self.get_doc_before_save()
		previous = before.status if before else None
		if self.is_new() and self.status != "Draft":
			frappe.throw(_("A new Work Instruction starts as a Draft"))
		if not allowed_template_transition(previous, self.status):
			frappe.throw(
				_("A Work Instruction cannot go from {0} to {1}").format(_(previous), _(self.status))
			)
		if before and previous != "Draft" and self._content_changed(before):
			frappe.throw(
				_("Revision {0} is {1} and cannot be edited. Make a new revision instead.").format(
					self.revision, _(previous)
				)
			)
		if not self.steps:
			frappe.throw(_("A Work Instruction needs at least one step"))
		problems = []
		for step in self.steps:
			problems.extend(validate_template_step(step.as_dict()))
		if problems:
			frappe.throw("<br>".join(frappe.utils.escape_html(p) for p in problems), title=_("Steps"))
		self.estimated_minutes = estimated_minutes([s.as_dict() for s in self.steps])
		if self.status == "Released" and previous != "Released":
			if not set(frappe.get_roles()) & set(RELEASE_ROLES):
				frappe.throw(
					_("Only {0} can release a Work Instruction").format(", ".join(RELEASE_ROLES)),
					frappe.PermissionError,
				)
			self.released_at, self.released_by = now_datetime(), frappe.session.user

	def on_update(self):
		before = self.get_doc_before_save()
		if self.status == "Released" and (not before or before.status != "Released"):
			# Only one revision of a code is in use at a time.
			for name in frappe.get_all(
				"Work Instruction",
				filters={
					"instruction_code": self.instruction_code,
					"status": "Released",
					"name": ("!=", self.name),
				},
				pluck="name",
			):
				older = frappe.get_doc("Work Instruction", name)
				older.status = "Obsolete"
				older.save(ignore_permissions=True)

	def _content_changed(self, before) -> bool:
		if any(self.get(f) != before.get(f) for f in HEADER_FIELDS):
			return True
		mine = [tuple(s.get(f) for f in STEP_FIELDS) for s in self.steps]
		theirs = [tuple(s.get(f) for f in STEP_FIELDS) for s in before.steps]
		return mine != theirs


@frappe.whitelist(methods=["POST"])
def release(name: str) -> dict:
	"""Release a Draft revision for use; the revision of the same code in use becomes Obsolete."""
	doc = frappe.get_doc("Work Instruction", name)
	doc.check_permission("write")
	if doc.status != "Released":
		doc.status = "Released"
		doc.save()
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def make_obsolete(name: str) -> dict:
	doc = frappe.get_doc("Work Instruction", name)
	doc.check_permission("write")
	if doc.status != "Obsolete":
		doc.status = "Obsolete"
		doc.save()
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def new_revision(name: str, change_note: str | None = None) -> dict:
	"""A Draft copy of `name` as the next revision of its code, for editing and release."""
	source = frappe.get_doc("Work Instruction", name)
	frappe.has_permission("Work Instruction", "create", throw=True)
	doc = frappe.copy_doc(source)
	doc.update(
		{
			"status": "Draft",
			"revision": next_revision(source.instruction_code),
			"released_at": None,
			"released_by": None,
			"amended_from_revision": source.name,
			"change_note": change_note,
		}
	)
	doc.insert()
	return {"name": doc.name, "revision": doc.revision}


def instructions_for(machine: str | None = None, machine_type: str | None = None) -> list[dict]:
	"""Released instructions that apply at a machine: those for the machine itself, those for its
	machine type with no machine set, and those with neither set, most specific first."""
	wi = frappe.qb.DocType("Work Instruction")
	rows = (
		frappe.qb.from_(wi)
		.select(
			wi.name,
			wi.instruction_code,
			wi.revision,
			wi.title,
			wi.operation,
			wi.machine,
			wi.machine_type,
			wi.estimated_minutes,
			wi.governing_sop,
		)
		.where(wi.status == "Released")
		.orderby(wi.instruction_code)
		.run(as_dict=True)
	)
	out = []
	for r in rows:
		if r.machine:
			if r.machine != machine:
				continue
			r["scope"] = "Machine"
		elif r.machine_type:
			if not machine_type or r.machine_type != machine_type:
				continue
			r["scope"] = "Machine Type"
		else:
			r["scope"] = "All Machines"
		out.append(r)
	order = {"Machine": 0, "Machine Type": 1, "All Machines": 2}
	out.sort(key=lambda r: (order[r["scope"]], r.instruction_code))
	return out


@frappe.whitelist()
def list_instructions_for_machine(machine: str | None = None) -> list[dict]:
	"""Released instructions an operator can start at `machine` (or that apply everywhere)."""
	frappe.has_permission("Work Instruction", "read", throw=True)
	machine_type = frappe.db.get_value("Machine", machine, "machine_type") if machine else None
	return instructions_for(machine, machine_type)
