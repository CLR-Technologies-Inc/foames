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

"""Utility consumption per period and meter, and per good unit made where the zone serves a line.

Each meter point is charged to the zone its asset serves (or sits in). A totalizer's consumption is
the increase between readings by the machine-counter rules; a rate meter is integrated. Readings of
Bad quality are left out. The reading just before the window is used so the first increase in the
window counts. Consumption per good unit uses the good counts of the machines whose Line is the
zone's Production Line, in the same period (an ISO 50001 energy performance indicator).
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from foames.foames_bms import bms
from foames.foames_mes.counters import GOOD_COUNTERS
from foames.foames_mes.report.utils import chart_of, date_window, summary_item

PERIODS = ("Day", "Week", "Month")
RATE_HOURS = {"Hour": 1.0, "Minute": 1 / 60.0, "Second": 1 / 3600.0}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = consumption_rows(filters)
	columns = [
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Date", "width": 100},
		{"fieldname": "utility", "label": _("Utility"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "zone",
			"label": _("Zone"),
			"fieldtype": "Link",
			"options": "Facility Zone",
			"width": 140,
		},
		{
			"fieldname": "facility_asset",
			"label": _("Facility Asset"),
			"fieldtype": "Link",
			"options": "Facility Asset",
			"width": 140,
		},
		{
			"fieldname": "point",
			"label": _("Meter"),
			"fieldtype": "Link",
			"options": "Building Point",
			"width": 160,
		},
		{
			"fieldname": "consumption",
			"label": _("Consumption"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{"fieldname": "unit", "label": _("Unit"), "fieldtype": "Data", "width": 70},
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 100},
		{
			"fieldname": "good_units",
			"label": _("Good Units"),
			"fieldtype": "Float",
			"precision": 0,
			"width": 100,
		},
		{
			"fieldname": "per_unit",
			"label": _("Per Good Unit"),
			"fieldtype": "Float",
			"precision": 4,
			"width": 120,
		},
	]
	totals = {}
	for row in rows:
		key = (row["utility"], row["unit"] or "")
		totals[key] = totals.get(key, 0.0) + row["consumption"]
	summary = [
		summary_item(f"{utility} ({unit})" if unit else utility, flt(total, 3))
		for (utility, unit), total in sorted(totals.items())
	]
	chart = None
	if filters.get("utility") and rows:
		periods = sorted({r["period"] for r in rows})
		chart = chart_of(
			[str(p) for p in periods],
			[
				{
					"name": filters.utility,
					"values": [
						flt(sum(r["consumption"] for r in rows if r["period"] == p), 3) for p in periods
					],
				}
			],
		)
	return columns, rows, None, chart, summary


def consumption_rows(filters) -> list[dict]:
	period = filters.get("period") or "Day"
	if period not in PERIODS:
		frappe.throw(_("Period must be Day, Week or Month"))
	start, end = date_window(filters)
	assets = assets_in_scope(filters)
	if not assets:
		return []
	conditions = {"point_type": "Meter", "disabled": 0, "facility_asset": ("in", list(assets))}
	if filters.get("utility"):
		conditions["utility"] = filters.utility
	meters = frappe.get_list(
		"Building Point",
		filters=conditions,
		fields=[
			"name",
			"facility_asset",
			"utility",
			"unit",
			"meter_mode",
			"rollover",
			"rate_time_base",
			"max_gap_minutes",
		],
		order_by="name",
	)
	zone_lines = dict(frappe.get_all("Facility Zone", fields=["name", "line"], as_list=True))
	good_by_line: dict[str, dict] = {}
	rows = []
	for meter in meters:
		readings = meter_readings(meter.name, start, end)
		used = bms.consumption_by_period(
			meter.meter_mode or "Totalizer",
			readings,
			period,
			rollover=meter.rollover or None,
			max_gap_minutes=meter.max_gap_minutes or 60,
			per_hours=RATE_HOURS.get(meter.rate_time_base or "Hour", 1.0),
		)
		zone = assets[meter.facility_asset]
		line = zone_lines.get(zone) if zone else None
		if line and line not in good_by_line:
			good_by_line[line] = good_units(line, start, end, period)
		for bucket, amount in sorted(used.items()):
			if not (start.date() <= bucket < end.date()):
				continue
			good = good_by_line.get(line, {}).get(bucket, 0.0) if line else None
			rows.append(
				{
					"period": bucket,
					"utility": meter.utility,
					"zone": zone,
					"facility_asset": meter.facility_asset,
					"point": meter.name,
					"consumption": flt(amount, 6),
					"unit": meter.unit,
					"line": line,
					"good_units": good,
					"per_unit": bms.intensity(amount, good) if good else None,
				}
			)
	rows.sort(key=lambda r: (r["period"], r["utility"] or "", r["point"]))
	return rows


def assets_in_scope(filters) -> dict[str, str | None]:
	"""Facility Asset -> the zone its consumption is charged to (the zone it serves, else where it is)."""
	from foames.foames_bms.api import zone_and_children

	conditions = {"disabled": 0}
	if filters.get("facility_asset"):
		conditions["name"] = filters.facility_asset
	rows = frappe.get_list("Facility Asset", filters=conditions, fields=["name", "zone", "serves_zone"])
	zones = set(zone_and_children(filters.zone)) if filters.get("zone") else None
	out = {}
	for row in rows:
		charged = row.serves_zone or row.zone
		if zones is None or charged in zones:
			out[row.name] = charged
	return out


def meter_readings(point: str, start, end) -> list[tuple]:
	"""(timestamp, value) of a point's usable readings in [start, end), with the last one before."""
	usable = ("in", ("Good", "Uncertain"))
	before = frappe.get_all(
		"Building Point Reading",
		filters=[["point", "=", point], ["timestamp", "<", start], ["quality", "in", ["Good", "Uncertain"]]],
		fields=["timestamp", "value"],
		order_by="timestamp desc",
		limit_page_length=1,
	)
	inside = frappe.get_all(
		"Building Point Reading",
		filters={"point": point, "timestamp": ("between", (start, end)), "quality": usable},
		fields=["timestamp", "value"],
		order_by="timestamp asc",
	)
	rows = list(reversed(before)) + [r for r in inside if get_datetime(r.timestamp) < end]
	return [(get_datetime(r.timestamp), float(r.value or 0)) for r in rows]


def good_units(line: str, start, end, period: str) -> dict:
	"""Good units made on a line per period: the Count deltas of its machines' good counters."""
	machines = frappe.get_all("Machine", filters={"line": line}, pluck="name")
	if not machines:
		return {}
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.timestamp, event.delta)
		.where(
			(event.machine.isin(machines))
			& (event.event_type == "Count")
			& (event.counter_name.isin(list(GOOD_COUNTERS)))
			& (event.timestamp >= start)
			& (event.timestamp < end)
		)
		.run(as_dict=True)
	)
	out: dict = {}
	for row in rows:
		bucket = bms.period_start(get_datetime(row.timestamp), period)
		out[bucket] = out.get(bucket, 0.0) + float(row.delta or 0)
	return out
