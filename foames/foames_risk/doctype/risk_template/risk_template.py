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

from foames.foames_risk.risk import check_rating


class RiskTemplate(Document):
	def validate(self):
		for field in ("inherent_impact", "inherent_likelihood"):
			if self.get(field):
				try:
					check_rating(self.get(field), self.meta.get_label(field))
				except ValueError as e:
					frappe.throw(_(str(e)))
