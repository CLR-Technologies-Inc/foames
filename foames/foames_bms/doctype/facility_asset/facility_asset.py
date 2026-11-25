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

"""Facility equipment or a utility system the BMS watches. Its status follows its points."""

import frappe
from frappe.model.document import Document

from foames.foames_bms import bms


class FacilityAsset(Document):
	def validate(self):
		self.title = self.title or self.asset_name
		if not self.equipment_class:
			self.equipment_class = bms.default_equipment_class(self.system)
		if not self.haystack_tags:
			self.haystack_tags = bms.default_equipment_tags(self.system)
		if self.system != "Hazardous Material Storage":
			self.hazard_assessment = None
		if not self.is_new() and self.has_value_changed("out_of_service"):
			self.status, self.active_alarms = status_of(self.name, bool(self.out_of_service))

	def on_update(self):
		if self.has_value_changed("out_of_service") and self.out_of_service:
			# Out of service: its open alarms stop asking for attention.
			from foames.foames_bms.engine import close_asset_suggestions

			close_asset_suggestions(self.name)


def status_of(asset: str, out_of_service: bool) -> tuple[str, int]:
	points = [
		{"condition": p.alarm_condition, "last_value_at": p.last_value_at, "disabled": p.disabled}
		for p in frappe.get_all(
			"Building Point",
			filters={"facility_asset": asset},
			fields=["alarm_condition", "last_value_at", "disabled"],
		)
	]
	active = frappe.db.count(
		"Building Alarm", {"facility_asset": asset, "status": ("in", ("Active", "Acknowledged"))}
	)
	return bms.asset_status(points, out_of_service), active


def refresh_status(asset: str) -> str:
	"""Recompute an asset's status and active alarm count from its points, without touching Modified."""
	out_of_service = bool(frappe.db.get_value("Facility Asset", asset, "out_of_service"))
	status, active = status_of(asset, out_of_service)
	frappe.db.set_value(
		"Facility Asset", asset, {"status": status, "active_alarms": active}, update_modified=False
	)
	return status
