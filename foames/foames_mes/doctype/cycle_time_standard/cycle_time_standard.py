# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""An operation's standard time split into automatic (machine) and manual (operator) elements.

The arithmetic is in `foames.foames_mes.cycle_time`; this class only validates the record and stores
the one-cycle figures it computes, so lists and reports can show them without recomputing.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_mes.cycle_time import breakdown, problems, standard_from_dict


class CycleTimeStandard(Document):
	def validate(self):
		self.validate_references()
		for row in self.elements:
			# An empty Every N Cycles means every cycle.
			if not row.every_n_cycles:
				row.every_n_cycles = 1
		standard = self.as_standard()
		errors = problems(standard)
		if errors:
			frappe.throw("<br>".join(errors), title=_("Cycle Time Standard"))
		if self.is_default and not self.machine:
			frappe.throw(_("A default standard needs a machine"))
		self.apply_breakdown(breakdown(standard))

	def on_update(self):
		if self.is_default and self.machine:
			# One default per machine: the newest one wins.
			others = frappe.get_all(
				"Cycle Time Standard",
				filters={"machine": self.machine, "is_default": 1, "name": ("!=", self.name)},
				pluck="name",
			)
			for name in others:
				frappe.db.set_value("Cycle Time Standard", name, "is_default", 0)

	def validate_references(self):
		for field, expected in (("operation_reference", "Operation"), ("item_reference", "Item")):
			name = self.get(field)
			if not name:
				continue
			kind = frappe.db.get_value("External Reference", name, "reference_type")
			if kind and kind != expected:
				frappe.throw(
					_("{0} must be an External Reference of type {1}, not {2}").format(
						_(self.meta.get_label(field)), _(expected), kind
					)
				)

	def as_standard(self):
		return standard_from_dict(
			{
				"name": self.name,
				"parts_per_cycle": self.parts_per_cycle,
				"allowance_percent": self.allowance_percent,
				"labor_rate": self.labor_rate,
				"machine_rate": self.machine_rate,
				"elements": [row.as_dict() for row in self.elements],
			}
		)

	def apply_breakdown(self, b):
		d = b.as_dict()
		for field in (
			"cycle_seconds",
			"automatic_seconds",
			"manual_seconds",
			"manual_external_seconds",
			"manual_internal_seconds",
			"machine_waits_seconds",
			"automation_percent",
			"machines_per_operator",
		):
			self.set(field, d[field] or 0)
		self.setup_seconds = d["setup_manual_seconds"] + d["setup_automatic_seconds"]
