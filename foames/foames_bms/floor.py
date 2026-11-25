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

"""Building systems on the floor snapshot (the `foames_floor_snapshot_extensions` hook): per system,
how many assets are in alarm or stale, and the open building alarms, so the floor page, the rules
and agents see facility problems next to the machines they may affect."""

import frappe

from foames.foames_bms import bms


def extend_snapshot(snapshot: dict, since, now):
	if not frappe.has_permission("Facility Asset", "read"):
		return
	from foames.foames_bms.api import facility_summary

	summary = facility_summary()
	summary["alarms"] = frappe.get_all(
		"Building Alarm",
		filters={"status": ("in", bms.OPEN_ALARM_STATUSES)},
		fields=[
			"name",
			"facility_asset",
			"system",
			"zone",
			"priority",
			"alarm_condition",
			"status",
			"raised_at",
		],
		order_by="raised_at desc",
		limit_page_length=50,
	)
	snapshot["facility"] = summary
