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

"""One value a building controller or meter reports, with its alarm limits and present value."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_bms import bms


class BuildingPoint(Document):
	def validate(self):
		self.point_id = (self.point_id or "").strip()
		self.title = self.title or self.point_id
		if self.point_type == "Meter":
			if not self.utility:
				frappe.throw(_("A meter point needs its utility"))
			self.meter_mode = self.meter_mode or "Totalizer"
		else:
			self.utility = None
		if self.point_type == "Status" and not self.quantity:
			self.quantity = "Run Status"
		if self.value_kind == "Binary" and not self.limits and self.point_type == "Alarm":
			self.append("limits", {"limit_type": "Alarm State", "value": 1, "priority": "Medium"})
		problems = bms.check_limits(self.limit_dicts())
		if problems:
			frappe.throw(_("Check the alarm limits: {0}").format("; ".join(problems)))
		if (self.deadband or 0) < 0:
			frappe.throw(_("The deadband cannot be negative"))
		if not self.brick_class:
			self.brick_class = bms.default_point_class(self.point_type, self.quantity)
		if not self.haystack_tags:
			self.haystack_tags = bms.default_point_tags(self.point_type, self.quantity, self.utility)
		self.alarm_condition = self.alarm_condition or bms.NORMAL

	def on_update(self):
		if self.has_value_changed("facility_asset") or self.has_value_changed("disabled"):
			from foames.foames_bms.doctype.facility_asset.facility_asset import refresh_status

			refresh_status(self.facility_asset)
			before = self.get_doc_before_save()
			if before and before.facility_asset and before.facility_asset != self.facility_asset:
				refresh_status(before.facility_asset)

	def limit_dicts(self) -> list[dict]:
		return [
			{
				"limit_type": row.limit_type,
				"value": row.value,
				"priority": row.priority or "Medium",
				"delay_seconds": row.delay_seconds or 0,
			}
			for row in self.limits
		]
