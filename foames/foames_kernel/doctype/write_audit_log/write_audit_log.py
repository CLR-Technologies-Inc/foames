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


class WriteAuditLog(Document):
	"""One entry of the append-only, hash-chained log of everything the write gate did."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Audit entries cannot be changed"))
		if not self.flags.foames_audit:
			frappe.throw(_("Audit entries are written by the write gate only"))

	def on_trash(self):
		frappe.throw(_("Audit entries cannot be deleted"))
