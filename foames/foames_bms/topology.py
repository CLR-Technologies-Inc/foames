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

"""The building systems in the topology graph (the `foames_topology_collectors` hook).

Facility zones and assets become Physical-layer assets (zones as Site or Area, assets as Equipment
inside their zone), and building points become Data-layer signals bound to their asset, carrying the
present value. The report goes through the same provider and tenant checks as any collector.
"""

import frappe

PROVIDER = "foames-bms"
STATUS = {
	"Normal": "OK",
	"Alarm": "OK",
	"Stale": "Stale",
	"Out of Service": "Maintenance",
	"Unknown": "Unknown",
}


def zone_id(name: str) -> str:
	return f"bms-zone:{name}"


def asset_id(name: str) -> str:
	return f"bms-asset:{name}"


def point_id(name: str) -> str:
	return f"bms-point:{name}"


def report() -> dict:
	assets, bindings = [], []
	for zone in frappe.get_all(
		"Facility Zone",
		filters={"disabled": 0},
		fields=["name", "zone_type", "parent_facility_zone", "line"],
		order_by="lft",
	):
		assets.append(
			{
				"asset_id": zone_id(zone.name),
				"title": zone.name,
				"layer": "Physical",
				"kind": "Site" if zone.zone_type == "Site" else "Area",
				"parent_asset": zone_id(zone.parent_facility_zone) if zone.parent_facility_zone else None,
				"attributes": {"zone_type": zone.zone_type, "line": zone.line},
			}
		)
	for asset in frappe.get_all(
		"Facility Asset",
		filters={"disabled": 0},
		fields=["name", "title", "system", "zone", "serves_zone", "status", "equipment_class"],
		order_by="name",
	):
		assets.append(
			{
				"asset_id": asset_id(asset.name),
				"title": asset.title or asset.name,
				"layer": "Physical",
				"kind": "Equipment",
				"parent_asset": zone_id(asset.zone) if asset.zone else None,
				"status": STATUS.get(asset.status, "Unknown"),
				"attributes": {
					"system": asset.system,
					"bms_status": asset.status,
					"brick_class": asset.equipment_class,
					"serves_zone": asset.serves_zone,
				},
			}
		)
	for point in frappe.get_all(
		"Building Point",
		filters={"disabled": 0},
		fields=[
			"name",
			"title",
			"facility_asset",
			"point_type",
			"quantity",
			"unit",
			"last_value",
			"last_value_at",
			"alarm_condition",
			"stale_after_minutes",
			"brick_class",
			"haystack_tags",
		],
		order_by="name",
	):
		assets.append(
			{
				"asset_id": point_id(point.name),
				"title": point.title or point.name,
				"layer": "Data",
				"kind": "Signal",
				"status": "Stale"
				if point.alarm_condition == "Stale"
				else ("OK" if point.last_value_at else "Unknown"),
				"last_seen": point.last_value_at,
				"attributes": {
					"point_type": point.point_type,
					"quantity": point.quantity,
					"condition": point.alarm_condition,
					"brick_class": point.brick_class,
					"haystack_tags": point.haystack_tags,
				},
			}
		)
		bindings.append(
			{
				"signal": point_id(point.name),
				"physical_asset": asset_id(point.facility_asset),
				"direction": "Read",
				"unit": point.unit,
				"tag": point.name,
				"last_value": point.last_value if point.last_value_at else None,
				"last_value_at": point.last_value_at,
				"stale_after_seconds": (point.stale_after_minutes or 60) * 60,
			}
		)
	return {"provider": PROVIDER, "assets": assets, "bindings": bindings, "retire_missing": True}
