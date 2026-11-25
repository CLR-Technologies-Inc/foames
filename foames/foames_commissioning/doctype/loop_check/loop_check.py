# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""A loop check: one instrument or signal checked from the field device to the control system.

Analog loops are checked at points across the calibrated range: the expected value at each point is
worked out from the range, and the as-left reading (or the as-found reading when the loop was not
adjusted) must be within the tolerance, as a percent of span. Digital loops are checked in each
state. A failed loop raises one punch item of the loop's category (A by default, as a loop that does
not work blocks start-up).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_commissioning.commissioning import (
	ANALOG,
	default_points,
	evaluate_analog_point,
	evaluate_digital_point,
	loop_status,
)
from foames.foames_commissioning.doctype.commissioning_package.commissioning_package import (
	check_package_open,
	check_tag_in_scope,
	refresh_package,
)


class LoopCheck(Document):
	def validate(self):
		check_package_open(self.package, _("loop checks"))
		self.tag = (self.tag or "").strip()
		self.machine = check_tag_in_scope(self.package, self.equipment_tag)
		analog = self.loop_type in ANALOG
		if analog and float(self.range_high or 0) == float(self.range_low or 0):
			frappe.throw(_("An analog loop needs a calibrated range with a span"))
		if not self.points:
			for point in default_points(self.loop_type):
				self.append("points", point)
		results = []
		for point in self.points:
			if analog:
				for field in ("as_found", "as_left"):
					value = (point.get(field) or "").strip()
					point.set(field, value)
					if value:
						try:
							float(value)
						except ValueError:
							frappe.throw(
								_("Row {0}: {1} must be a number").format(
									point.idx, point.meta.get_label(field)
								)
							)
				evaluated = evaluate_analog_point(
					point.percent_of_span,
					self.range_low,
					self.range_high,
					self.tolerance_percent,
					as_found=point.as_found,
					as_left=point.as_left,
				)
				point.expected_value = evaluated["expected"]
				point.error_percent = evaluated["error_percent"]
				point.result = evaluated["result"]
			else:
				if not point.expected_state:
					frappe.throw(_("Row {0}: a digital point needs its expected state").format(point.idx))
				point.result = evaluate_digital_point(point.expected_state, point.observed_state)
			results.append(point.result)
		self.status = loop_status(results, checked_by=self.checked_by, cancelled=bool(self.cancelled))
		self.checked_on = (self.checked_on or now_datetime()) if self.status == "Passed" else None

	def on_update(self):
		if self.status == "Failed" and not self.punch_item:
			failed = [p for p in self.points if p.result == "Fail"]
			detail = "\n".join(
				_("Point {0}: expected {1}, found {2}").format(
					p.idx,
					p.expected_state or f"{p.expected_value:g} {self.engineering_unit or ''}".strip(),
					p.observed_state or p.as_left or p.as_found,
				)
				for p in failed
			)
			punch = frappe.get_doc(
				{
					"doctype": "Punch Item",
					"package": self.package,
					"title": _("Loop check of {0} failed").format(self.tag),
					"details": detail,
					"category": self.punch_category or "A",
					"equipment_tag": self.equipment_tag,
					"source_doctype": self.doctype,
					"source_name": self.name,
				}
			).insert(ignore_permissions=True)
			self.db_set("punch_item", punch.name, update_modified=False)
		refresh_package(self.package)

	def on_trash(self):
		frappe.db.set_value(
			"Punch Item",
			{"source_doctype": self.doctype, "source_name": self.name},
			{"source_doctype": None, "source_name": None},
		)

	def after_delete(self):
		refresh_package(self.package)
