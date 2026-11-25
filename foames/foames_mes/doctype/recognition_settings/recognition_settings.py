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

"""How recognition shows on the floor, what FoaMES recognizes on its own, and who opted out.
Read it through foames.foames_mes.doctype.recognition.recognition.recognition_settings, which fills
in the defaults for values never saved."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_mes.recognition import parse_thresholds


class RecognitionSettings(Document):
	def validate(self):
		seen = set()
		for row in self.opt_out:
			if row.user in seen:
				frappe.throw(_("{0} is listed twice").format(row.user))
			seen.add(row.user)
		self.milestone_thresholds = ",".join(str(t) for t in parse_thresholds(self.milestone_thresholds))
