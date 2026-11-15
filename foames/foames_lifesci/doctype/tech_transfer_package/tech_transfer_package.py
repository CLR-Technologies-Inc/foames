# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""An MSAT tech transfer package.

A draft may be incomplete; its problems are shown on save. Submitting is approval: it is refused
while the package has problems (foames.foames_lifesci.transfer.package_problems), when a CQA names
a requirement the linked PRD does not have, or when the approver prepared the package. After
approval only the deliverables' progress changes; a change to the process is an amendment.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from foames.foames_lifesci import transfer

PARAMETER_FIELDS = (
	"parameter",
	"criticality",
	"limits",
	"set_point",
	"nor_low",
	"nor_high",
	"par_low",
	"par_high",
	"scale_dependent",
	"scale_rule",
	"justification",
)
ATTRIBUTE_FIELDS = (
	"attribute",
	"criticality",
	"limits",
	"lower",
	"upper",
	"approach",
	"margin",
	"k",
	"analytical_method",
	"requirement_id",
)
TRANSFER_TEMPLATE = (
	"Transfer plan and protocol",
	"Gap analysis: equipment, facility, materials and utilities at the receiving site",
	"Quality risk assessment of the transfer",
	"Analytical method transfer",
	"Training of receiving-site staff",
	"Engineering or demonstration batch",
	"Process performance qualification (PPQ)",
	"Comparability assessment of the CQAs",
	"Transfer report",
)


class TechTransferPackage(Document):
	def validate(self):
		if self.is_new() or not self.prepared_by:
			self.prepared_by = frappe.session.user
		if self.is_new() and not self.deliverables:
			for name in TRANSFER_TEMPLATE:
				self.append("deliverables", {"deliverable": name, "required": 1})
		self.scale_ratio = transfer.scale_ratio(flt(self.from_scale), flt(self.to_scale)) or 0
		for row in self.parameters:
			value = (
				transfer.scale_set_point(flt(row.set_point), row.scale_rule, self.scale_ratio)
				if (row.scale_rule and self.scale_ratio)
				else None
			)
			row.receiving_set_point = value
		problems = self.problems()
		if problems and not self.flags.ignore_problems:
			frappe.msgprint(
				"<br>".join(problems), title=_("Open before approval"), indicator="orange", alert=False
			)

	def problems(self):
		params = [{"idx": r.idx, **{f: r.get(f) for f in PARAMETER_FIELDS}} for r in self.parameters]
		attrs = [{"idx": r.idx, **{f: r.get(f) for f in ATTRIBUTE_FIELDS}} for r in self.attributes]
		problems = transfer.package_problems(params, attrs)
		if self.product_requirements:
			known = set(
				frappe.get_all(
					"Product Requirement",
					filters={
						"parent": self.product_requirements,
						"parenttype": "Product Requirements Document",
					},
					pluck="req_id",
				)
			)
			for a in attrs:
				if a["requirement_id"] and a["requirement_id"] not in known:
					problems.append(
						_("{0}: requirement {1} is not in {2}").format(
							a["attribute"], a["requirement_id"], self.product_requirements
						)
					)
		return problems

	def before_submit(self):
		problems = self.problems()
		if problems:
			frappe.throw("<br>".join(problems), title=_("The package cannot be approved"))
		if frappe.session.user == self.prepared_by:
			frappe.throw(
				_("A tech transfer package is approved by someone other than the person who prepared it")
			)

	def on_submit(self):
		self.db_set({"approved_by": frappe.session.user, "approved_on": now_datetime()})

	def attribute(self, name):
		return next((a for a in self.attributes if a.attribute == name), None)
