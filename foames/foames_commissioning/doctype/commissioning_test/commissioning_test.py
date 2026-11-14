# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One commissioning test (FAT, SAT, mechanical completion and so on) with its steps.

Value steps are judged against their limits as readings are entered; Check and Text steps take the
tester's result. A failed step raises a punch item of the step's category, once. The test passes
when every step passed or does not apply and the performer, and the witness when one is required,
signed it off.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_commissioning.commissioning import evaluate_step, sequence_blockers, status_of_test
from foames.foames_commissioning.doctype.commissioning_package.commissioning_package import (
	check_package_open,
	check_tag_in_scope,
	refresh_package,
)


class CommissioningTest(Document):
	def before_insert(self):
		if self.template and not self.steps:
			self.copy_template()

	def validate(self):
		check_package_open(self.package, _("tests"))
		self.machine = check_tag_in_scope(self.package, self.equipment_tag)
		if self.template:
			template = frappe.db.get_value(
				"Commissioning Checklist Template",
				self.template,
				["test_type", "witness_required"],
				as_dict=True,
			)
			if template and template.test_type != self.test_type:
				frappe.throw(
					_("Template {0} is for {1}, not {2}").format(
						self.template, template.test_type, self.test_type
					)
				)
		if not self.title:
			self.title = f"{self.test_type} {self.equipment_tag}" if self.equipment_tag else self.test_type
		for step in self.steps:
			self.evaluate(step)
		previous = self.get_doc_before_save()
		previous_status = previous.status if previous else "Not Started"
		self.status = status_of_test(
			[step.result for step in self.steps],
			performed_by=self.performed_by,
			witness_required=bool(self.witness_required),
			witnessed_by=self.witnessed_by,
			cancelled=bool(self.cancelled),
		)
		if self.status not in ("Not Started", "Cancelled"):
			if previous_status == "Not Started":
				self.check_sequence()
			self.started_on = self.started_on or now_datetime()
		if self.witnessed_by and not self.witnessed_on:
			self.witnessed_on = now_datetime()
		self.completed_on = (self.completed_on or now_datetime()) if self.status == "Passed" else None

	def evaluate(self, step):
		for field in ("low_limit", "high_limit", "measured_value"):
			value = (step.get(field) or "").strip() if isinstance(step.get(field), str) else step.get(field)
			step.set(field, value)
			if step.kind == "Value" and value not in (None, ""):
				try:
					float(value)
				except (TypeError, ValueError):
					frappe.throw(
						_("Row {0}: {1} must be a number, not {2}").format(
							step.idx, step.meta.get_label(field), value
						)
					)
		step.result = evaluate_step(
			step.kind, step.measured_value, step.low_limit, step.high_limit, step.result
		)

	def check_sequence(self):
		"""A test cannot start while an earlier-stage test on the same equipment has not passed, when
		the package enforces the sequence. A test of the whole package (no equipment tag) is held by,
		and holds, tests of every piece of equipment."""
		if not frappe.db.get_value("Commissioning Package", self.package, "enforce_sequence"):
			return
		others = [
			t
			for t in frappe.get_all(
				"Commissioning Test",
				filters={"package": self.package, "name": ("!=", self.name or "")},
				fields=["name", "test_type", "status", "equipment_tag"],
			)
			if not t.equipment_tag or not self.equipment_tag or t.equipment_tag == self.equipment_tag
		]
		blockers = sequence_blockers(self.test_type, others)
		if blockers:
			frappe.throw(
				_("{0} cannot start before these tests pass: {1}").format(
					self.test_type,
					", ".join(f"{b['test_type']} {b['name']} ({b['status']})" for b in blockers),
				)
			)

	def copy_template(self):
		template = frappe.get_doc("Commissioning Checklist Template", self.template)
		if template.disabled:
			frappe.throw(_("Template {0} is disabled").format(self.template))
		if template.witness_required:
			self.witness_required = 1
		for item in template.items:
			self.append(
				"steps",
				{
					"section": item.section,
					"check_text": item.check_text,
					"kind": item.kind,
					"acceptance_criteria": item.acceptance_criteria,
					"low_limit": item.low_limit,
					"high_limit": item.high_limit,
					"unit": item.unit,
					"punch_category": item.punch_category or "B",
				},
			)

	def on_update(self):
		self.raise_punch_items()
		refresh_package(self.package)

	def on_trash(self):
		frappe.db.set_value(
			"Punch Item",
			{"source_doctype": self.doctype, "source_name": self.name},
			{"source_doctype": None, "source_name": None},
		)

	def after_delete(self):
		refresh_package(self.package)

	def raise_punch_items(self):
		"""One punch item for each failed step that has none yet."""
		for step in self.steps:
			if step.result != "Fail" or step.punch_item:
				continue
			reading = (
				f" (measured {step.measured_value} {step.unit or ''})".rstrip() if step.measured_value else ""
			)
			punch = frappe.get_doc(
				{
					"doctype": "Punch Item",
					"package": self.package,
					"title": _("{0} step {1} failed: {2}").format(self.test_type, step.idx, step.check_text)[
						:140
					],
					"details": f"{step.check_text}{reading}\n{step.acceptance_criteria or ''}\n{step.remarks or ''}".strip(),
					"category": step.punch_category or "B",
					"equipment_tag": self.equipment_tag,
					"source_doctype": self.doctype,
					"source_name": self.name,
					"source_step": step.idx,
				}
			).insert(ignore_permissions=True)
			step.db_set("punch_item", punch.name, update_modified=False)
