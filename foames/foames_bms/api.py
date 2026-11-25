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

"""Building management readings in, and the read methods agents and pages use.

POST JSON to /api/method/foames.foames_bms.api.ingest_point_readings with {"readings": [...]} (or one
reading, or a list), signed exactly like the machine-event webhook (foames.foames_mes.signing, with
the webhook secret in Machine Data Settings). Each reading is {"point": "<Building Point id>",
"value": 21.4, "timestamp": "...", "quality": "Good", "id": "<optional source id>"}. Unsigned calls
need a logged-in user with FoaMES Operator, Engineer or System Manager.

Everything else here only reads.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from foames.foames_bms import bms

MAX_ROWS = 500


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep
def ingest_point_readings():
	from foames.foames_bms.engine import record_readings
	from foames.foames_mes.api import _authorised

	body = frappe.request.get_data() if frappe.request else b""
	if not _authorised(body):
		frappe.throw(_("Invalid or missing signature"), frappe.AuthenticationError)
	try:
		data = json.loads(body or b"{}")
	except ValueError:
		frappe.throw(_("Body must be JSON"))
	if isinstance(data, list):
		readings = data
	elif isinstance(data, dict) and "readings" in data:
		readings = data.get("readings")
	else:
		readings = [data]
	if not isinstance(readings, list):
		frappe.throw(_("readings must be a list"))
	source = "Webhook" if frappe.session.user == "Guest" else "Manual"
	return record_readings(readings, source=source)


def _limit(limit, default=100) -> int:
	try:
		return max(1, min(int(limit or default), MAX_ROWS))
	except (TypeError, ValueError):
		frappe.throw(_("limit must be a number"))


@frappe.whitelist()
def list_facility_assets(
	system: str | None = None, zone: str | None = None, status: str | None = None, limit: int = 100
) -> list[dict]:
	"""Facility assets with their system, zone, status and active alarm count."""
	frappe.has_permission("Facility Asset", "read", throw=True)
	filters = {"disabled": 0}
	if system:
		filters["system"] = system
	if status:
		filters["status"] = status
	if zone:
		filters["zone"] = ("in", zone_and_children(zone))
	return frappe.get_list(
		"Facility Asset",
		filters=filters,
		fields=[
			"name",
			"title",
			"system",
			"zone",
			"serves_zone",
			"status",
			"active_alarms",
			"out_of_service",
			"equipment_class",
			"hazard_assessment",
		],
		order_by="system, name",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def get_facility_asset(asset: str) -> dict:
	"""One asset with its points' present values and its open alarms."""
	doc = frappe.get_doc("Facility Asset", asset)
	doc.check_permission("read")
	out = doc.as_dict(no_default_fields=True)
	out["points"] = frappe.get_list(
		"Building Point",
		filters={"facility_asset": asset},
		fields=[
			"name",
			"title",
			"point_type",
			"quantity",
			"unit",
			"utility",
			"last_value",
			"last_value_at",
			"last_quality",
			"alarm_condition",
			"open_alarm",
			"disabled",
		],
		order_by="name",
	)
	out["open_alarms"] = frappe.get_list(
		"Building Alarm",
		filters={"facility_asset": asset, "status": ("in", bms.OPEN_ALARM_STATUSES)},
		fields=["name", "point", "status", "priority", "alarm_condition", "raised_at", "last_value"],
		order_by="raised_at desc",
	)
	return out


@frappe.whitelist()
def list_building_alarms(
	status: str | None = None,
	priority: str | None = None,
	system: str | None = None,
	zone: str | None = None,
	facility_asset: str | None = None,
	limit: int = 100,
) -> list[dict]:
	"""Building alarms, open ones (Active, Acknowledged, Returned) unless a status is given."""
	frappe.has_permission("Building Alarm", "read", throw=True)
	filters = {"status": status} if status else {"status": ("in", bms.OPEN_ALARM_STATUSES)}
	if priority:
		filters["priority"] = priority
	if system:
		filters["system"] = system
	if facility_asset:
		filters["facility_asset"] = facility_asset
	if zone:
		filters["zone"] = ("in", zone_and_children(zone))
	return frappe.get_list(
		"Building Alarm",
		filters=filters,
		fields=[
			"name",
			"point",
			"facility_asset",
			"system",
			"zone",
			"status",
			"priority",
			"alarm_condition",
			"raised_at",
			"value_at_raise",
			"limit_value",
			"worst_value",
			"last_value",
			"unit",
			"acknowledged_by",
			"returned_at",
		],
		order_by="raised_at desc",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def get_point_history(
	point: str, since: str | None = None, until: str | None = None, limit: int = 500
) -> dict:
	"""A point's readings, oldest first, in [since, until) (default the last 24 hours)."""
	doc = frappe.get_doc("Building Point", point)
	doc.check_permission("read")
	frappe.has_permission("Building Point Reading", "read", throw=True)
	until = get_datetime(until) if until else now_datetime()
	since = get_datetime(since) if since else add_to_date(until, hours=-24)
	readings = frappe.get_list(
		"Building Point Reading",
		filters=[["point", "=", point], ["timestamp", ">=", since], ["timestamp", "<", until]],
		fields=["timestamp", "value", "quality"],
		order_by="timestamp asc",
		limit_page_length=_limit(limit, MAX_ROWS),
	)
	return {
		"point": doc.name,
		"title": doc.title,
		"unit": doc.unit,
		"point_type": doc.point_type,
		"since": since,
		"until": until,
		"readings": readings,
	}


@frappe.whitelist()
def get_utility_consumption(
	from_date: str | None = None,
	to_date: str | None = None,
	period: str = "Day",
	utility: str | None = None,
	zone: str | None = None,
	facility_asset: str | None = None,
) -> list[dict]:
	"""Utility consumption per period and meter, with consumption per good unit where the zone serves
	a production line. The rows of the Utility Consumption report."""
	from foames.foames_bms.report.utility_consumption.utility_consumption import consumption_rows

	frappe.has_permission("Building Point Reading", "read", throw=True)
	filters = frappe._dict(
		from_date=from_date,
		to_date=to_date,
		period=period or "Day",
		utility=utility,
		zone=zone,
		facility_asset=facility_asset,
	)
	return consumption_rows(filters)


@frappe.whitelist()
def get_facility_summary() -> dict:
	"""Per system: assets, assets in alarm or stale, open alarms by priority. For dashboards and the
	floor snapshot."""
	frappe.has_permission("Facility Asset", "read", throw=True)
	return facility_summary()


def facility_summary() -> dict:
	systems: dict[str, dict] = {}
	for asset in frappe.get_all(
		"Facility Asset", filters={"disabled": 0}, fields=["name", "system", "status"]
	):
		row = systems.setdefault(
			asset.system, {"assets": 0, "alarm": 0, "stale": 0, "out_of_service": 0, "open_alarms": {}}
		)
		row["assets"] += 1
		key = {"Alarm": "alarm", "Stale": "stale", "Out of Service": "out_of_service"}.get(asset.status)
		if key:
			row[key] += 1
	for alarm in frappe.get_all(
		"Building Alarm",
		filters={"status": ("in", bms.OPEN_ALARM_STATUSES)},
		fields=["system", "priority"],
	):
		row = systems.setdefault(
			alarm.system or "Other",
			{"assets": 0, "alarm": 0, "stale": 0, "out_of_service": 0, "open_alarms": {}},
		)
		row["open_alarms"][alarm.priority] = row["open_alarms"].get(alarm.priority, 0) + 1
	return {"systems": systems, "open_alarms": sum(sum(r["open_alarms"].values()) for r in systems.values())}


def zone_and_children(zone: str) -> list[str]:
	"""A zone and every zone below it in the tree."""
	bounds = frappe.db.get_value("Facility Zone", zone, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return [zone]
	return frappe.get_all(
		"Facility Zone",
		filters={"lft": (">=", bounds.lft), "rgt": ("<=", bounds.rgt)},
		pluck="name",
	)


def mcp_tools():
	"""The building management read tools for the MCP server (the `foames_mcp_tools` hook)."""
	from foames.foames_mcp.protocol import Tool

	base = "foames.foames_bms.api"

	def s(description, **extra):
		return {"type": "string", "description": description, **extra}

	def schema(properties, required=None):
		out = {"type": "object", "properties": properties, "additionalProperties": False}
		if required:
			out["required"] = required
		return out

	limit = {
		"type": "integer",
		"description": "Rows to return (at most 500)",
		"minimum": 1,
		"maximum": MAX_ROWS,
	}
	zone = s("A Facility Zone; zones inside it are included")
	system = s("Only this system", enum=list(bms.SYSTEMS))
	return [
		Tool(
			name="foames_bms_list_assets",
			title="List facility assets",
			description="Building systems FoaMES watches (HVAC, RTUs, chillers, water, wastewater, electricity, lighting, server rooms, hazmat storage) with status and active alarm count. Reads only. Needs read on Facility Asset.",
			method=f"{base}.list_facility_assets",
			input_schema=schema(
				{
					"system": system,
					"zone": zone,
					"status": s(
						"Only this status", enum=["Unknown", "Normal", "Alarm", "Stale", "Out of Service"]
					),
					"limit": limit,
				}
			),
		),
		Tool(
			name="foames_bms_get_asset",
			title="Get a facility asset",
			description="One facility asset with every point's present value and condition, and its open alarms. Reads only.",
			method=f"{base}.get_facility_asset",
			input_schema=schema({"asset": s("Facility Asset id")}, ["asset"]),
		),
		Tool(
			name="foames_bms_list_alarms",
			title="List building alarms",
			description="Building alarms, the open ones (Active, Acknowledged, Returned) unless a status is given, newest first. Reads only; acknowledging is for people.",
			method=f"{base}.list_building_alarms",
			input_schema=schema(
				{
					"status": s("Only this status", enum=list(bms.ALARM_STATUSES)),
					"priority": s("Only this priority", enum=list(bms.PRIORITIES)),
					"system": system,
					"zone": zone,
					"facility_asset": s("Only this Facility Asset"),
					"limit": limit,
				}
			),
		),
		Tool(
			name="foames_bms_point_history",
			title="Building point history",
			description="Readings of one building point, oldest first, default the last 24 hours. Reads only. Needs read on Building Point Reading.",
			method=f"{base}.get_point_history",
			input_schema=schema(
				{
					"point": s("Building Point id"),
					"since": s("Start, ISO 8601 site time"),
					"until": s("End, ISO 8601 site time"),
					"limit": limit,
				},
				["point"],
			),
		),
		Tool(
			name="foames_bms_utility_consumption",
			title="Utility consumption",
			description="Utility consumption (electricity, gas, water, wastewater, chilled water, steam, compressed air) per day, week or month and meter, with consumption per good unit where the zone serves a production line. Reads only.",
			method=f"{base}.get_utility_consumption",
			input_schema=schema(
				{
					"from_date": s("First day, YYYY-MM-DD (default 30 days ago)"),
					"to_date": s("Last day, YYYY-MM-DD (default today)"),
					"period": s("Bucket size", enum=["Day", "Week", "Month"]),
					"utility": s("Only this utility", enum=list(bms.UTILITIES)),
					"zone": zone,
					"facility_asset": s("Only this Facility Asset"),
				}
			),
		),
		Tool(
			name="foames_bms_summary",
			title="Facility summary",
			description="Per building system: assets, assets in alarm, stale or out of service, and open alarms by priority. Reads only.",
			method=f"{base}.get_facility_summary",
		),
	]
