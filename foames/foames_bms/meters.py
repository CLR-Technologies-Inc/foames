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

"""Maintenance meters for facility equipment, read from its building points.

A Maintenance Plan on a Facility Asset (a chiller, an RTU, a pump) wears the same way a machine's
does: by calendar, by run hours or by count. Run hours come from the asset's run-status point (a
Status point with quantity Run Status), held between readings for at most the point's Max Gap, so a
point that stops reporting stops wearing on paper. Count comes from one of its totalizing meters (the
plan's Counter Name, or the asset's first totalizer), by the machine-counter rules.
"""

import frappe
from frappe.utils import add_to_date

from foames.foames_bms import bms


def _readings(point: str, since, until, lookback_minutes: int) -> list[tuple]:
	rows = frappe.get_all(
		"Building Point Reading",
		filters=[
			["point", "=", point],
			["timestamp", ">=", add_to_date(since, minutes=-lookback_minutes)],
			["timestamp", "<", until],
			["quality", "in", ["Good", "Uncertain"]],
		],
		fields=["timestamp", "value"],
		order_by="timestamp asc",
	)
	return [(r.timestamp, float(r.value or 0)) for r in rows]


def run_status_point(asset: str) -> frappe._dict | None:
	return frappe.db.get_value(
		"Building Point",
		{"facility_asset": asset, "point_type": "Status", "quantity": "Run Status", "disabled": 0},
		["name", "max_gap_minutes"],
		as_dict=True,
		order_by="name asc",
	)


def run_hours(asset: str, since, until) -> float:
	point = run_status_point(asset)
	if not point or until <= since:
		return 0.0
	gap = point.max_gap_minutes or 60
	return bms.run_hours(_readings(point.name, since, until, gap), since, until, gap)


def totalizer_point(asset: str, counter_name: str | None = None) -> frappe._dict | None:
	filters = {"facility_asset": asset, "point_type": "Meter", "meter_mode": "Totalizer", "disabled": 0}
	if counter_name:
		filters["name"] = counter_name
	return frappe.db.get_value(
		"Building Point", filters, ["name", "rollover"], as_dict=True, order_by="name asc"
	)


def count(asset: str, since, until, counter_name: str | None = None) -> float:
	point = totalizer_point(asset, counter_name)
	if not point or until <= since:
		return 0.0
	# Only readings inside the window: the increase since the last service, nothing before it.
	return bms.totalizer_consumption(_readings(point.name, since, until, 0), point.rollover or None)
