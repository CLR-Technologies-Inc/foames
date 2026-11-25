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

from foames.foames_risk.risk import RATINGS, normalise_bands


class RiskSettings(Document):
	def validate(self):
		try:
			bands = normalise_bands(
				{
					"Very Low": self.very_low_max,
					"Low": self.low_max,
					"Moderate": self.moderate_max,
					"High": self.high_max,
				}
			)
		except ValueError as e:
			frappe.throw(_(str(e)))
		self.very_low_max, self.low_max, self.moderate_max, self.high_max = (bands[r] for r in RATINGS[:-1])
		for field in ("review_days", "high_risk_review_days", "verification_days"):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(_(self.meta.get_label(field))))
