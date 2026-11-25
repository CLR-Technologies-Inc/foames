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

"""Every enabled Lineside Bin with its line-dry forecast: stock on hand, use per hour, hours until it
runs dry against the time a replenishment takes, and what to call for. Worst first, then soonest dry.

Values are as the 10-minute material check last stored them; "Check now" on a bin refreshes one.
"""

import frappe
from frappe import _

from foames.foames_mes.material import BIN_STATUSES
from foames.foames_mes.report.utils import chart_of, machines_in_scope, summary_item

RANK = {status: index for index, status in enumerate(reversed(BIN_STATUSES))}
AT_RISK = ("Running Dry", "Will Run Dry", "Dry")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = forecast_rows(filters)
	counts = {status: sum(1 for r in rows if r["status"] == status) for status in BIN_STATUSES}
	return (
		get_columns(),
		rows,
		None,
		chart_of(
			[_(s) for s in BIN_STATUSES[1:]],
			[{"name": _("Bins"), "values": [counts[s] for s in BIN_STATUSES[1:]]}],
			colors=["#E24C4C"],
		)
		if rows
		else None,
		[
			summary_item(_("Dry"), counts["Dry"], "Int", "Red"),
			summary_item(_("Will Run Dry"), counts["Will Run Dry"], "Int", "Red"),
			summary_item(_("Running Dry"), counts["Running Dry"], "Int", "Orange"),
			summary_item(_("Reorder"), counts["Reorder"], "Int", "Yellow"),
		],
	)


def forecast_rows(filters) -> list[dict]:
	conditions = {"disabled": 0}
	if filters.get("machine") or filters.get("line"):
		machines = machines_in_scope(filters)
		if not machines:
			return []
		conditions["machine"] = ("in", list(machines))
	if filters.get("item"):
		conditions["item"] = filters.item
	if filters.get("at_risk_only"):
		conditions["status"] = ("in", AT_RISK)
	rows = frappe.get_list(
		"Lineside Bin",
		filters=conditions,
		fields=[
			"name",
			"title",
			"machine",
			"item",
			"uom",
			"status",
			"on_hand",
			"in_transit_qty",
			"per_hour",
			"hours_to_dry",
			"dry_at",
			"replenishment_lead_minutes",
			"replenish_qty",
			"replenishment_method",
			"mpc_level",
			"last_checked",
		],
	)
	for r in rows:
		r["lead_hours"] = (r.pop("replenishment_lead_minutes") or 0) / 60.0
	big = float("inf")
	rows.sort(
		key=lambda r: (RANK.get(r["status"], 9), r["hours_to_dry"] if r["hours_to_dry"] is not None else big)
	)
	return rows


def get_columns():
	return [
		{
			"label": _("Bin"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Lineside Bin",
			"width": 110,
		},
		{"label": _("Title"), "fieldname": "title", "fieldtype": "Data", "width": 180},
		{
			"label": _("Machine"),
			"fieldname": "machine",
			"fieldtype": "Link",
			"options": "Machine",
			"width": 110,
		},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Data", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("On Hand"), "fieldname": "on_hand", "fieldtype": "Float", "width": 90},
		{"label": _("Unit"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
		{"label": _("In Transit"), "fieldname": "in_transit_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Use / Hour"), "fieldname": "per_hour", "fieldtype": "Float", "width": 90},
		{"label": _("Hours to Dry"), "fieldname": "hours_to_dry", "fieldtype": "Float", "width": 100},
		{"label": _("Lead (h)"), "fieldname": "lead_hours", "fieldtype": "Float", "width": 80},
		{"label": _("Runs Dry Around"), "fieldname": "dry_at", "fieldtype": "Datetime", "width": 150},
		{"label": _("Call For"), "fieldname": "replenish_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Method"), "fieldname": "replenishment_method", "fieldtype": "Data", "width": 100},
		{"label": _("MPC"), "fieldname": "mpc_level", "fieldtype": "Int", "width": 60},
		{"label": _("Checked"), "fieldname": "last_checked", "fieldtype": "Datetime", "width": 150},
	]
