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

"""A product requirements document and its trace matrix.

Submitting is approval, by someone other than the person who prepared it. After approval only the
trace columns of each requirement (design output, verification, validation) change, as the work
is done; a change to the requirements themselves is an amendment, a new revision. The coverage
figures are kept current on every save. The rules are in foames.foames_life_sciences.requirements.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_life_sciences import requirements

TRACE_FIELDS = (
	"req_id",
	"level",
	"parent_req",
	"requirement",
	"critical",
	"acceptance_criteria",
	"verification_method",
	"design_output",
	"verification_reference",
	"verification_status",
	"validation_reference",
	"risk_reference",
)


class ProductRequirementsDocument(Document):
	def validate(self):
		if self.is_new() or not self.prepared_by:
			self.prepared_by = frappe.session.user
		for row in self.requirements:
			row.req_id = (row.req_id or "").strip()
			row.parent_req = (row.parent_req or "").strip() or None
		problems = requirements.requirement_problems(self.requirement_rows())
		if problems:
			frappe.throw("<br>".join(problems), title=_("Requirements are not consistent"))
		self.refresh_coverage()

	def before_update_after_submit(self):
		self.refresh_coverage()

	def before_submit(self):
		if frappe.session.user == self.prepared_by:
			frappe.throw(
				_("A requirements document is approved by someone other than the person who prepared it")
			)

	def on_submit(self):
		self.db_set({"approved_by": frappe.session.user, "approved_on": now_datetime()})

	def requirement_rows(self):
		return [{"idx": r.idx, **{f: r.get(f) for f in TRACE_FIELDS}} for r in self.requirements]

	def trace(self):
		return requirements.trace_matrix(self.requirement_rows())

	def refresh_coverage(self):
		trace = self.trace()
		self.percent_verified = trace["percent_verified"]
		self.percent_refined = trace["percent_refined"]
		self.open_gaps = len(trace["gaps"])

	@frappe.whitelist()
	def get_trace_matrix(self):
		self.check_permission("read")
		return self.trace()
