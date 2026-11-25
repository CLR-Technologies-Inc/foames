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

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_mes.andon import DEFAULT_CALL_TYPES


class AndonCallType(Document):
	def validate(self):
		if not self.title:
			self.title = self.code
		for field in ("acknowledge_within_minutes", "resolve_within_minutes"):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(_(self.meta.get_label(field))))


def create_default_call_types():
	"""The standard call types, created once on install and by a patch; edit or disable them freely."""
	for values in DEFAULT_CALL_TYPES:
		if not frappe.db.exists("Andon Call Type", values["code"]):
			frappe.get_doc({"doctype": "Andon Call Type", **values}).insert(ignore_permissions=True)
