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

"""Industrial hygiene monitoring: an 8-hour time-weighted average, or a noise dose, against its limit
and action level. A result at or above the action level raises an Agent Suggestion."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_ehs.ehs import evaluate_exposure, exposure_findings


class ExposureRecord(Document):
	def validate(self):
		if not self.samples:
			frappe.throw(_("Add at least one sample"))
		if self.method == "Noise":
			self.unit = "dBA"
		try:
			result = evaluate_exposure(
				self.method,
				[(s.value, s.minutes) for s in self.samples],
				self.limit,
				self.action_level,
				self.shift_minutes,
			)
		except ValueError as error:
			frappe.throw(_(str(error)[0].upper() + str(error)[1:]))
		self.limit = result["limit"]
		self.action_level = result["action_level"]
		self.result = result["result"]
		self.dose_percent = result["dose_percent"]
		self.percent_of_limit = result["percent_of_limit"]
		self.status = result["status"]

	def on_update(self):
		from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

		raise_suggestions(exposure_findings(self.as_dict()), agent="foames-ehs")
