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

"""A person's record that they read, or were trained on, one SOP revision.

Records are made through the SOP's Acknowledge and Record Training actions. One record per person
and revision; the SOP code and revision are copied on so that the training matrix can tell an
acknowledgement of an earlier revision (Outdated) from none at all (Missing).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class SOPAcknowledgement(Document):
	def validate(self):
		sop = frappe.db.get_value(
			"Standard Operating Procedure", self.sop, ["sop_code", "revision"], as_dict=True
		)
		if not sop:
			frappe.throw(_("SOP {0} not found").format(self.sop))
		self.sop_code, self.revision = sop.sop_code, sop.revision
		if self.is_new():
			self.acknowledged_on = self.acknowledged_on or now_datetime()
			if frappe.db.exists("SOP Acknowledgement", {"sop": self.sop, "user": self.user}):
				frappe.throw(_("{0} has already acknowledged {1}").format(self.user, self.sop))
		else:
			before = self.get_doc_before_save()
			if before and (before.sop != self.sop or before.user != self.user):
				frappe.throw(_("An acknowledgement cannot be moved to another SOP or person"))
