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

from foames.foames_adapters import get_adapters


class FoaMESSettings(Document):
	def validate(self):
		if self.default_erp_system and self.default_erp_system not in get_adapters():
			frappe.throw(_("{0} is not a registered ERP system").format(frappe.bold(self.default_erp_system)))

	def on_update(self):
		from foames.foames_kernel.write_gate import log_settings_change

		log_settings_change(self)
