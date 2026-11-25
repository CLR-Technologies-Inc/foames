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

"""A validation or qualification protocol: what is tested, how, and what counts as passing.

Submitting the protocol approves it; it is then executed through Validation Executions and changed
only by cancelling and amending it, so every execution points at the text it was run against.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

from foames.foames_validation import qualification as q


class ValidationProtocol(Document):
	def validate(self):
		try:
			kind = q.protocol_type(self.protocol_type)
		except ValueError as e:
			frappe.throw(str(e))
		self.validation_stage = kind["stage"]
		if not cint(self.required_runs) or cint(self.required_runs) < 1:
			self.required_runs = kind["default_runs"]
		if cint(self.validity_months) < 0:
			frappe.throw(_("Validity cannot be negative"))
		if self.protocol_type in q.EQUIPMENT_TYPES and not self.machine:
			frappe.throw(
				_("A {0} protocol qualifies one machine; set the Machine").format(self.protocol_type)
			)
		if self.protocol_type in q.PROCESS_TYPES and not (self.process_name or "").strip():
			frappe.throw(_("A {0} protocol validates a process; set the Process").format(self.protocol_type))
		if not self.criteria:
			frappe.throw(_("A protocol needs at least one acceptance criterion"))
		for row in self.criteria:
			self.validate_criterion(row)

	def validate_criterion(self, row):
		label = _("Row {0} ({1})").format(row.idx, row.criterion)
		if row.check_type not in q.CHECK_TYPES:
			frappe.throw(_("{0}: unknown check {1}").format(label, row.check_type))
		if row.check_type != "Numeric Range":
			row.source = "Machine Data" if row.check_type in q.MACHINE_DATA_TYPES else "Manual"
		row.source = row.source or "Manual"
		if row.check_type in ("Numeric Range", "Capability"):
			row.limits = row.limits or "Lower and Upper"
			lower, upper = criterion_limits(row)
			if lower is not None and upper is not None and upper < lower:
				frappe.throw(_("{0}: the upper limit is below the lower limit").format(label))
		if row.source == "Machine Data":
			if not (row.measurement or "").strip():
				frappe.throw(_("{0}: name the measurement to read from machine data").format(label))
			if not (row.machine or self.machine):
				frappe.throw(_("{0}: name the machine to read, here or on the protocol").format(label))
		if row.check_type == "Capability":
			row.capability_index = row.capability_index or "Cpk"
			if row.min_index in (None, "") or flt(row.min_index) <= 0:
				row.min_index = q.DEFAULT_MIN_INDEX
		if row.check_type in q.MACHINE_DATA_TYPES and cint(row.min_points) < 2:
			row.min_points = q.DEFAULT_MIN_POINTS
		if row.check_type == "Statistical Control":
			row.rule_set = row.rule_set or "Nelson"

	def on_submit(self):
		self.db_set({"approved_by": frappe.session.user, "approved_on": now_datetime()})


def criterion_limits(row) -> tuple:
	"""(lower, upper) of a criterion or result row, None on the side its Limits leave open. Frappe
	stores an empty Float as 0, so the Limits select says which sides are real."""
	if row.check_type not in ("Numeric Range", "Capability"):
		return None, None
	limits = row.limits or "Lower and Upper"
	lower = None if limits == "Upper Only" else flt(row.lower_limit)
	upper = None if limits == "Lower Only" else flt(row.upper_limit)
	return lower, upper
