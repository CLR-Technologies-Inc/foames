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

"""Building point readings in, alarms and suggestions out.

`record_readings` stores what a gateway, historian bridge or person sends and runs each new reading
through its point's limits (`bms.step`). A reading older than the point's present value is stored for
history and consumption but does not move the alarm state. A Bad-quality reading is stored and marks
the point's quality, and is not compared with the limits.

Alarms: one open Building Alarm per point at a time. A new condition raises one; a more or less
severe condition moves it (and asks for a new acknowledgement); a return to normal closes it when it
was acknowledged, or leaves it Returned until someone does. Each raise and change becomes an Agent
Suggestion, unless the asset is out of service. FoaMES never writes back to the BMS.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from foames.foames_bms import bms

AGENT = "foames-bms"
ASSET_FIELDS = ["name", "system", "zone", "out_of_service", "disabled", "hazard_assessment"]


def _raise(findings: list[dict]) -> list[str]:
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	return raise_suggestions(findings, agent=AGENT)


def record_readings(readings: list, source: str = "Manual") -> dict:
	"""Store a batch of raw readings. Returns {"accepted": [names], "rejected": [{reading, reason}]}."""
	from foames.foames_mes.api import site_timezone

	tz = site_timezone()
	accepted, rejected = [], []
	points: dict[str, dict | None] = {}
	for raw in readings or []:
		try:
			reading = bms.normalise_reading(raw, tz=tz)
			point = points.get(reading["point"], False)
			if point is False:
				point = frappe.db.get_value(
					"Building Point", reading["point"], ["name", "disabled"], as_dict=True
				)
				points[reading["point"]] = point
			if not point or point.disabled:
				raise bms.ReadingError(f"no enabled Building Point has id {reading['point']!r}")
			accepted.append(store_reading(reading, source))
		except bms.ReadingError as e:
			rejected.append({"reading": raw, "reason": str(e)})
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			rejected.append({"reading": raw, "reason": "duplicate reading id"})
	return {"accepted": accepted, "rejected": rejected}


def store_reading(reading: dict, source: str = "Manual") -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Building Point Reading",
			"point": reading["point"],
			"timestamp": reading["timestamp"],
			"value": reading["value"],
			"quality": reading["quality"],
			"reading_key": reading["reading_key"],
			"source": source,
		}
	).insert(ignore_permissions=True)
	apply_reading(reading["point"], reading)
	return doc.name


def apply_reading(point_name: str, reading: dict) -> str | None:
	"""Move a point's present value and alarm state with a new reading. Returns the action taken."""
	point = frappe.get_doc("Building Point", point_name)
	at = get_datetime(reading["timestamp"])
	if point.last_value_at and at < get_datetime(point.last_value_at):
		return None
	first = not point.last_value_at
	if reading["quality"] == "Bad":
		frappe.db.set_value("Building Point", point.name, "last_quality", "Bad", update_modified=False)
		return None
	value = float(reading["value"])
	state = {
		"condition": point.alarm_condition or bms.NORMAL,
		"pending_condition": point.pending_condition or None,
		"pending_since": get_datetime(point.pending_since) if point.pending_since else None,
	}
	new_state, action, limit = bms.step(state, value, at, point.limit_dicts(), point.deadband or 0)
	updates = {
		"last_value": value,
		"last_value_at": at,
		"last_quality": reading["quality"],
		"alarm_condition": new_state["condition"],
		"pending_condition": new_state["pending_condition"],
		"pending_since": new_state["pending_since"],
	}
	frappe.db.set_value("Building Point", point.name, updates, update_modified=False)
	point.update(updates)
	if action:
		_act(point, action, limit, value, at)
	if action or first:
		from foames.foames_bms.doctype.facility_asset.facility_asset import refresh_status

		refresh_status(point.facility_asset)
	return action


def _asset(name: str) -> frappe._dict:
	return frappe.db.get_value("Facility Asset", name, ASSET_FIELDS, as_dict=True) or frappe._dict()


def _act(point, action: str, limit: dict | None, value: float | None, at):
	"""Raise, change, update or return the point's open alarm."""
	alarm = frappe.get_doc("Building Alarm", point.open_alarm) if point.open_alarm else None
	if alarm and alarm.status == "Closed":
		alarm = None
	if action == "return":
		if alarm:
			return_alarm(alarm, value, at)
		frappe.db.set_value("Building Point", point.name, "open_alarm", None, update_modified=False)
		return
	condition = point.alarm_condition
	priority = (limit or {}).get("priority") or point.stale_priority or "Medium"
	limit_value = (limit or {}).get("value")
	if action == "update" and alarm:
		alarm.last_value = value
		alarm.worst_value = bms.worse(condition, alarm.worst_value, value)
		alarm.save(ignore_permissions=True)
		return
	if alarm is None:
		alarm = new_alarm(point, condition, priority, limit_value, value, at)
		frappe.db.set_value("Building Point", point.name, "open_alarm", alarm.name, update_modified=False)
		notify = True
	else:
		# Another condition on the same point: the open alarm moves. A more severe one needs
		# acknowledging again and asks people again; a less severe one keeps the acknowledgement.
		# Losing or regaining communication always asks again.
		escalated = bms.PRIORITY_RANK.get(priority, 9) < bms.PRIORITY_RANK.get(alarm.priority, 9)
		notify = escalated or bms.STALE in (condition, alarm.alarm_condition)
		worst = alarm.worst_value if value is None else bms.worse(condition, alarm.worst_value, value)
		alarm.update(
			{
				"alarm_condition": condition,
				"priority": priority,
				"limit_value": limit_value,
				"last_value": value,
				"worst_value": worst,
				"status": "Active" if notify or alarm.status == "Returned" else alarm.status,
				"returned_at": None,
			}
		)
		alarm.save(ignore_permissions=True)
	if notify and not _asset(point.facility_asset).get("out_of_service"):
		_raise([bms.alarm_finding(alarm_summary(alarm, point))])


def new_alarm(point, condition, priority, limit_value, value, at):
	asset = _asset(point.facility_asset)
	return frappe.get_doc(
		{
			"doctype": "Building Alarm",
			"point": point.name,
			"facility_asset": point.facility_asset,
			"system": asset.get("system"),
			"zone": asset.get("zone"),
			"hazard_assessment": asset.get("hazard_assessment"),
			"status": "Active",
			"priority": priority,
			"alarm_condition": condition,
			"raised_at": at,
			"value_at_raise": value,
			"limit_value": limit_value,
			"worst_value": value,
			"last_value": value,
			"unit": point.unit,
		}
	).insert(ignore_permissions=True)


def return_alarm(alarm, value, at):
	alarm.last_value = value if value is not None else alarm.last_value
	alarm.returned_at = at
	if alarm.status == "Acknowledged":
		alarm.status = "Closed"
		alarm.closed_at = at
	elif alarm.status == "Active":
		alarm.status = "Returned"
	alarm.save(ignore_permissions=True)
	if alarm.status == "Closed":
		alarm_handled(alarm)


def alarm_summary(alarm, point) -> dict:
	return {
		"name": alarm.name,
		"point": point.name,
		"point_title": point.title,
		"facility_asset": alarm.facility_asset,
		"system": alarm.system,
		"zone": alarm.zone,
		"condition": alarm.alarm_condition,
		"priority": alarm.priority,
		"value": alarm.last_value,
		"limit": alarm.limit_value,
		"unit": alarm.unit,
		"raised_at": alarm.raised_at,
		"last_value_at": point.last_value_at,
		"hazard_assessment": alarm.hazard_assessment,
	}


def _close_suggestions(filters: dict, status: str, resolution: str, from_statuses=("Open",)):
	for name in frappe.get_all(
		"Agent Suggestion", filters={**filters, "status": ("in", list(from_statuses))}, pluck="name"
	):
		suggestion = frappe.get_doc("Agent Suggestion", name)
		suggestion.status = status
		suggestion.resolution = resolution
		suggestion.save(ignore_permissions=True)


def alarm_handled(alarm):
	"""An alarm was acknowledged or closed: its open suggestions are Accepted, or Done once it closes."""
	if alarm.status == "Closed":
		status, resolution = "Done", _("Alarm {0} returned to normal and was acknowledged").format(alarm.name)
		from_statuses = ("Open", "Accepted")
	else:
		from_statuses = ("Open",)
		status, resolution = (
			"Accepted",
			_("Alarm {0} acknowledged by {1}").format(alarm.name, alarm.acknowledged_by),
		)
	_close_suggestions(
		{"reference_doctype": "Building Alarm", "reference_name": alarm.name, "agent": AGENT},
		status,
		resolution,
		from_statuses,
	)
	if alarm.facility_asset:
		from foames.foames_bms.doctype.facility_asset.facility_asset import refresh_status

		refresh_status(alarm.facility_asset)


def close_asset_suggestions(asset: str):
	"""An asset went out of service: the suggestions for its alarms are dismissed."""
	alarms = frappe.get_all("Building Alarm", filters={"facility_asset": asset}, pluck="name")
	if alarms:
		_close_suggestions(
			{"reference_doctype": "Building Alarm", "reference_name": ("in", alarms), "agent": AGENT},
			"Dismissed",
			_("{0} is out of service").format(asset),
		)


# Scheduled checks


def check_stale_points(now=None) -> list[str]:
	"""Every five minutes: points that stopped reporting get a communication-loss alarm. Returns the
	points that went stale."""
	now = get_datetime(now) if now else now_datetime()
	stale = []
	rows = frappe.get_all(
		"Building Point",
		filters={"disabled": 0, "last_value_at": ("is", "set"), "alarm_condition": ("!=", bms.STALE)},
		fields=["name", "last_value_at", "stale_after_minutes"],
	)
	for row in rows:
		if not bms.is_stale(get_datetime(row.last_value_at), now, row.stale_after_minutes):
			continue
		point = frappe.get_doc("Building Point", row.name)
		previous = point.alarm_condition or bms.NORMAL
		updates = {"alarm_condition": bms.STALE, "pending_condition": None, "pending_since": None}
		frappe.db.set_value("Building Point", point.name, updates, update_modified=False)
		point.update(updates)
		_act(point, "raise" if previous in (bms.NORMAL, "Unknown") else "change", None, point.last_value, now)
		from foames.foames_bms.doctype.facility_asset.facility_asset import refresh_status

		refresh_status(point.facility_asset)
		stale.append(point.name)
	return stale


def check_bms(now=None) -> list[str]:
	"""Hourly: Critical and High alarms nobody acknowledged, and hazardous material storage with no
	active hazard assessment or no monitored point. Returns the suggestions created or reopened."""
	now = get_datetime(now) if now else now_datetime()
	alarms = frappe.get_all(
		"Building Alarm",
		filters={"status": "Active", "priority": ("in", ("Critical", "High"))},
		fields=["name", "status", "priority", "alarm_condition", "point", "facility_asset", "raised_at"],
	)
	out_of_service = set(frappe.get_all("Facility Asset", filters={"out_of_service": 1}, pluck="name"))
	rows = [
		{**a, "condition": a.alarm_condition, "raised_at": get_datetime(a.raised_at)}
		for a in alarms
		if a.facility_asset not in out_of_service
	]
	findings = bms.unacknowledged_findings(rows, now)
	findings.extend(bms.hazmat_findings(hazmat_assets()))
	return _raise(findings)


def hazmat_assets() -> list[dict]:
	assets = frappe.get_all(
		"Facility Asset",
		filters={"system": "Hazardous Material Storage", "disabled": 0},
		fields=["name", "system", "out_of_service", "hazard_assessment"],
	)
	for asset in assets:
		asset["hazard_assessment_active"] = bool(
			asset.hazard_assessment
			and frappe.db.get_value("Hazard Assessment", asset.hazard_assessment, "status") == "Active"
		)
		asset["point_count"] = frappe.db.count(
			"Building Point", {"facility_asset": asset.name, "disabled": 0}
		)
	return assets
