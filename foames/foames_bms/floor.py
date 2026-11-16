# Copyright (c) 2026 CLR Technologies Inc. and contributors
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
