# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Building management as pure logic: the facility systems FoaMES watches, point readings, alarm
limits with deadband, staleness, utility consumption from meters and run hours from status points.
No Frappe dependency.

The building management system (BMS, also building automation system or BAS) runs the plant's
utilities and building services: water, wastewater, electricity, chilled water, HVAC, rooftop units,
chillers, lighting, server rooms, hazardous material storage and the like. They support production
without being on its process route, so FoaMES watches them and never commands them. Everything here
is established public practice:

- Points are the BACnet (ASHRAE 135) and Modbus idea of one readable value: a sensor, a setpoint, a
  status, a command or a meter. Each can carry Project Haystack tags and a Brick class so other tools
  can read the model; ASHRAE 223P builds on the same vocabulary.
- Alarm limits follow the usual analog alarm practice (and ISA-18.2 / IEC 62682 alarm management):
  high-high, high, low and low-low limits, each with a priority and an on-delay, and a deadband so a
  value hovering at a limit does not chatter. A binary point alarms when it reads its alarm state.
  A point that stops reporting is an alarm of its own (communication loss).
- Consumption from a totalising meter is the sum of the increases between readings, by the same rules
  as machine counters: a wrap counts only when the meter's rollover is known, and a reset counts
  nothing (nothing is invented). A rate meter (kW, m3/h, L/min) is integrated
  with the trapezoid rule, and a gap longer than the allowed one counts nothing rather than guessing.
- Energy intensity (consumption per good unit made) is the energy performance indicator of ISO 50001.

FoaMES does not write to a building controller: no setpoint, no command, no override (agents suggest;
people act). A future write would be a registered write action that passes the read-only write gate.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta
from itertools import pairwise

# The register

SYSTEMS = (
	"HVAC",
	"Air Handling Unit",
	"Rooftop Unit",
	"Chiller",
	"Cooling Tower",
	"Boiler",
	"Chilled Water",
	"Heating Hot Water",
	"Steam",
	"Domestic Water",
	"Process Water",
	"Wastewater",
	"Compressed Air",
	"Electricity",
	"Natural Gas",
	"Lighting",
	"Server Room",
	"Hazardous Material Storage",
	"Fire and Life Safety",
	"Other",
)

POINT_TYPES = ("Sensor", "Setpoint", "Status", "Command", "Alarm", "Meter")
VALUE_KINDS = ("Analog", "Binary", "Multistate")
QUANTITIES = (
	"Temperature",
	"Humidity",
	"Pressure",
	"Differential Pressure",
	"Flow",
	"Level",
	"Power",
	"Energy",
	"Current",
	"Voltage",
	"Volume",
	"Mass",
	"pH",
	"Conductivity",
	"Concentration",
	"CO2",
	"Run Status",
	"Position",
	"Speed",
	"Occupancy",
	"Leak",
	"Other",
)
UTILITIES = (
	"Electricity",
	"Natural Gas",
	"Water",
	"Wastewater",
	"Chilled Water",
	"Heating Hot Water",
	"Steam",
	"Compressed Air",
)
METER_MODES = ("Totalizer", "Rate")
PROTOCOLS = ("BACnet/IP", "Modbus TCP", "Historian", "Ignition", "OPC UA", "MQTT", "Manual", "Other")
QUALITIES = ("Good", "Uncertain", "Bad")

# Limits, from the most severe to the least. "Alarm State" is a binary or multistate point reading
# the state it alarms in.
LIMIT_TYPES = ("High High", "Low Low", "High", "Low", "Alarm State")
PRIORITIES = ("Critical", "High", "Medium", "Low")
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}
# Communication loss is its own condition, raised when a point stops reporting.
STALE = "Stale"
NORMAL = "Normal"
DEFAULT_STALE_MINUTES = 60
ALARM_STATUSES = ("Active", "Acknowledged", "Returned", "Closed")
OPEN_ALARM_STATUSES = ("Active", "Acknowledged", "Returned")

# Suggestion severity for an alarm priority.
SEVERITY = {"Critical": "Critical", "High": "Critical", "Medium": "Warning", "Low": "Info"}

# Brick classes (https://brickschema.org, BSD-3-Clause) and Project Haystack equipment markers
# (https://project-haystack.org, AFL-3.0) that fit each system. Only names are used, as the shared
# vocabulary both projects publish for exactly this; a site can override them per asset.
BRICK_EQUIPMENT = {
	"HVAC": "HVAC_Equipment",
	"Air Handling Unit": "Air_Handling_Unit",
	"Rooftop Unit": "Rooftop_Unit",
	"Chiller": "Chiller",
	"Cooling Tower": "Cooling_Tower",
	"Boiler": "Boiler",
	"Chilled Water": "Chilled_Water_System",
	"Heating Hot Water": "Hot_Water_System",
	"Electricity": "Electrical_System",
	"Lighting": "Lighting_System",
}
HAYSTACK_EQUIPMENT = {
	"Air Handling Unit": "equip ahu",
	"Rooftop Unit": "equip ahu rtu",
	"Chiller": "equip chiller",
	"Cooling Tower": "equip coolingTower",
	"Boiler": "equip boiler",
	"Chilled Water": "equip chilled water plant",
	"Heating Hot Water": "equip hot water plant",
	"Steam": "equip steam plant",
	"Domestic Water": "equip domestic water",
	"Electricity": "equip elec",
	"Natural Gas": "equip naturalGas",
	"Lighting": "equip lighting",
}
HAYSTACK_POINT = {"Sensor": "point sensor", "Setpoint": "point sp", "Command": "point cmd"}
HAYSTACK_QUANTITY = {
	"Temperature": "temp",
	"Humidity": "humidity",
	"Pressure": "pressure",
	"Differential Pressure": "pressure delta",
	"Flow": "flow",
	"Level": "level",
	"Power": "power",
	"Energy": "energy",
	"Current": "current",
	"Voltage": "volt",
	"Volume": "volume",
	"pH": "ph",
	"CO2": "co2",
	"Run Status": "run",
	"Speed": "speed",
	"Occupancy": "occupied",
}
BRICK_POINT = {
	("Sensor", "Temperature"): "Temperature_Sensor",
	("Sensor", "Humidity"): "Humidity_Sensor",
	("Sensor", "Pressure"): "Pressure_Sensor",
	("Sensor", "Differential Pressure"): "Differential_Pressure_Sensor",
	("Sensor", "Flow"): "Flow_Sensor",
	("Sensor", "Level"): "Level_Sensor",
	("Sensor", "Power"): "Power_Sensor",
	("Sensor", "Energy"): "Energy_Sensor",
	("Sensor", "Current"): "Current_Sensor",
	("Sensor", "Voltage"): "Voltage_Sensor",
	("Sensor", "CO2"): "CO2_Sensor",
	("Sensor", "Occupancy"): "Occupancy_Sensor",
	("Setpoint", "Temperature"): "Temperature_Setpoint",
	("Setpoint", "Humidity"): "Humidity_Setpoint",
	("Setpoint", "Pressure"): "Pressure_Setpoint",
	("Setpoint", "Flow"): "Flow_Setpoint",
	("Status", "Run Status"): "Run_Status",
	("Alarm", "Leak"): "Leak_Alarm",
	("Meter", "Energy"): "Energy_Sensor",
	("Meter", "Power"): "Power_Sensor",
}


def default_equipment_class(system: str) -> str | None:
	"""The Brick class for a system, when one fits it."""
	return BRICK_EQUIPMENT.get(system)


def default_equipment_tags(system: str) -> str:
	"""Haystack markers for a system's equipment (always at least `equip`)."""
	return HAYSTACK_EQUIPMENT.get(system, "equip")


def default_point_class(point_type: str, quantity: str | None) -> str | None:
	return BRICK_POINT.get((point_type, quantity))


def default_point_tags(point_type: str, quantity: str | None, utility: str | None = None) -> str:
	"""Haystack markers for a point: its kind, its quantity and, for a meter, its utility."""
	tags = [HAYSTACK_POINT.get(point_type, "point")]
	if quantity in HAYSTACK_QUANTITY:
		tags.append(HAYSTACK_QUANTITY[quantity])
	if point_type == "Meter":
		tags.append("meter")
	if utility:
		tags.append(utility_tag(utility))
	return " ".join(tags)


def utility_tag(utility: str) -> str:
	return {
		"Electricity": "elec",
		"Natural Gas": "naturalGas",
		"Water": "water",
		"Chilled Water": "chilled water",
		"Heating Hot Water": "hot water",
		"Steam": "steam",
		"Compressed Air": "air",
	}.get(utility, "")


def tag_set(text: str | None) -> set[str]:
	"""Haystack markers in a space- or comma-separated string."""
	return {t for t in (text or "").replace(",", " ").split() if t}


# Readings


class ReadingError(ValueError):
	pass


BINARY_WORDS = {
	"true": 1.0,
	"on": 1.0,
	"active": 1.0,
	"running": 1.0,
	"open": 1.0,
	"alarm": 1.0,
	"false": 0.0,
	"off": 0.0,
	"inactive": 0.0,
	"stopped": 0.0,
	"closed": 0.0,
	"normal": 0.0,
}


def reading_value(value) -> float:
	"""A reading's value as a number: numbers as they are, booleans and binary words as 1 or 0."""
	if isinstance(value, bool):
		return 1.0 if value else 0.0
	if isinstance(value, int | float):
		number = float(value)
	else:
		text = str(value if value is not None else "").strip()
		if text.lower() in BINARY_WORDS:
			return BINARY_WORDS[text.lower()]
		try:
			number = float(text)
		except ValueError:
			raise ReadingError(f"value {value!r} is not a number or a binary state")
	if not math.isfinite(number):
		raise ReadingError(f"value {value!r} is not finite")
	return number


def reading_quality(value) -> str:
	text = str(value or "Good").strip().lower()
	for quality in QUALITIES:
		if text == quality.lower():
			return quality
	raise ReadingError(f"quality must be one of {', '.join(QUALITIES)}")


def reading_key(point: str, timestamp: datetime, given: str | None = None) -> str:
	"""A unique key per point and sample, so a replayed reading is stored once."""
	if given:
		text = str(given).strip()
		if len(text) > 140:
			raise ReadingError("id is longer than 140 characters")
		return text
	digest = hashlib.sha256(f"{point}|{timestamp.isoformat()}".encode()).hexdigest()
	return f"bms:{digest[:40]}"


def normalise_reading(raw: dict, tz=None) -> dict:
	"""A raw reading {"point", "value", "timestamp", "quality", "id"} checked and normalised.

	Returns {"point", "value", "timestamp", "quality", "reading_key"}. Raises ReadingError."""
	from foames.foames_mes.gateway.mapping import EventError, parse_timestamp

	if not isinstance(raw, dict):
		raise ReadingError("a reading must be an object")
	point = str(raw.get("point") or raw.get("point_id") or "").strip()
	if not point:
		raise ReadingError("point is required")
	if "value" not in raw:
		raise ReadingError("value is required")
	try:
		timestamp = parse_timestamp(raw.get("timestamp"), tz=tz)
	except EventError as e:
		raise ReadingError(str(e))
	return {
		"point": point,
		"value": reading_value(raw.get("value")),
		"timestamp": timestamp,
		"quality": reading_quality(raw.get("quality")),
		"reading_key": reading_key(point, timestamp, raw.get("id")),
	}


# Limits and alarm conditions


def _float(value) -> float | None:
	if value is None or value == "":
		return None
	return float(value)


def check_limits(limits: list[dict]) -> list[str]:
	"""Problems with a point's limits: high-high below high, low-low above low, high not above low."""
	by_type = {}
	problems = []
	for limit in limits:
		kind = limit.get("limit_type")
		if kind not in LIMIT_TYPES:
			problems.append(f"unknown limit type {kind!r}")
			continue
		if kind in by_type:
			problems.append(f"{kind} is set twice")
			continue
		by_type[kind] = _float(limit.get("value"))
	hh, h, lo, ll = (by_type.get(k) for k in ("High High", "High", "Low", "Low Low"))
	if hh is not None and h is not None and hh < h:
		problems.append("High High is below High")
	if ll is not None and lo is not None and ll > lo:
		problems.append("Low Low is above Low")
	high = h if h is not None else hh
	low = lo if lo is not None else ll
	if high is not None and low is not None and high <= low:
		problems.append("the high limits must be above the low limits")
	return problems


def _exceeds(kind: str, value: float, limit: float, deadband: float, active: bool) -> bool:
	"""Whether `value` is past `limit`. An active condition clears only once the value is back
	inside the limit by the deadband, so a value hovering at the limit does not chatter."""
	band = deadband if active else 0.0
	if kind in ("High", "High High"):
		return value > limit - band if active else value > limit
	if kind in ("Low", "Low Low"):
		return value < limit + band if active else value < limit
	if kind == "Alarm State":
		return value == limit
	return False


def evaluate(
	value: float, limits: list[dict], current: str | None = None, deadband: float = 0
) -> dict | None:
	"""The limit `value` is past, the most severe first, or None when it is inside every limit.

	limits: dicts with limit_type, value, priority and delay_seconds. current: the point's present
	condition, which gets the deadband before it clears. Returns the limit dict that applies."""
	deadband = abs(float(deadband or 0))
	ordered = sorted(
		(
			lim
			for lim in limits
			if lim.get("limit_type") in LIMIT_TYPES and _float(lim.get("value")) is not None
		),
		key=lambda lim: LIMIT_TYPES.index(lim["limit_type"]),
	)
	for limit in ordered:
		kind = limit["limit_type"]
		if _exceeds(kind, float(value), float(limit["value"]), deadband, kind == current):
			return limit
	return None


def step(state: dict, value: float, at: datetime, limits: list[dict], deadband: float = 0) -> tuple:
	"""One reading through a point's alarm state. Returns (new_state, action, limit).

	state: {"condition", "pending_condition", "pending_since"}; condition is Normal, Unknown, Stale or
	a limit type. action is None, "raise" (a new alarm), "change" (the open alarm moves to another
	condition), "update" (the open alarm's condition holds) or "return" (back to normal). limit is the
	limit dict that applies, for raise, change and update. A condition with an on-delay is pending
	until a reading at least that much later still finds it."""
	current = state.get("condition") or NORMAL
	held = current if current in LIMIT_TYPES else None
	limit = evaluate(value, limits, held, deadband)
	if limit is None:
		action = "return" if current not in (NORMAL, "Unknown") else None
		return {"condition": NORMAL, "pending_condition": None, "pending_since": None}, action, None
	kind = limit["limit_type"]
	if kind == current:
		return {"condition": kind, "pending_condition": None, "pending_since": None}, "update", limit
	pending_since = state.get("pending_since") if state.get("pending_condition") == kind else at
	if condition_due(pending_since, at, limit.get("delay_seconds")):
		action = "raise" if current in (NORMAL, "Unknown") else "change"
		return {"condition": kind, "pending_condition": None, "pending_since": None}, action, limit
	return {"condition": current, "pending_condition": kind, "pending_since": pending_since}, None, None


def worse(kind: str, a: float | None, b: float) -> float:
	"""The value further past a limit of this kind."""
	if a is None:
		return b
	if kind in ("High", "High High"):
		return max(a, b)
	if kind in ("Low", "Low Low"):
		return min(a, b)
	return b


def condition_due(condition_since: datetime | None, at: datetime, delay_seconds) -> bool:
	"""Whether a condition that started at `condition_since` has lasted its on-delay by `at`."""
	if not delay_seconds:
		return True
	if condition_since is None:
		return False
	return (at - condition_since).total_seconds() >= float(delay_seconds)


def stale_minutes(point_minutes) -> int:
	return int(point_minutes or 0) or DEFAULT_STALE_MINUTES


def is_stale(last_at: datetime | None, now: datetime, minutes) -> bool:
	"""A point is stale when it has not reported for its stale time. A point that never reported
	is not stale (it is not commissioned yet), it is Unknown."""
	if last_at is None:
		return False
	return now - last_at > timedelta(minutes=stale_minutes(minutes))


def asset_status(points: list[dict], out_of_service: bool = False) -> str:
	"""An asset's status from its points: Out of Service, Alarm, Stale, Normal or Unknown."""
	if out_of_service:
		return "Out of Service"
	conditions = [p.get("condition") or NORMAL for p in points if not p.get("disabled")]
	if any(c not in (NORMAL, STALE, "Unknown") for c in conditions):
		return "Alarm"
	if any(c == STALE for c in conditions):
		return "Stale"
	if any(p.get("last_value_at") for p in points if not p.get("disabled")):
		return "Normal"
	return "Unknown"


# Consumption and run hours


def totalizer_consumption(readings: list[tuple[datetime, float]], rollover: float | None = None) -> float:
	"""Consumption from a totalising meter's readings, oldest first.

	The same rules as machine counters (foames.foames_mes.counters.counter_delta): increases are
	summed, a wrap counts only when the meter's rollover value is known, and a reset counts nothing."""
	from foames.foames_mes.counters import counter_delta

	total = 0.0
	previous = None
	for _at, value in readings:
		total += counter_delta(previous, value, rollover)
		previous = value
	return total


def rate_consumption(
	readings: list[tuple[datetime, float]], max_gap_minutes: float = 60, per_hours: float = 1.0
) -> float:
	"""Consumption from a rate meter's readings (oldest first), by the trapezoid rule.

	per_hours: the rate's time base in hours (1 for kW or m3/h, 1/60 for a per-minute rate). A gap
	longer than max_gap_minutes counts nothing; negative rates count as zero."""
	total = 0.0
	for (t0, v0), (t1, v1) in pairwise(readings):
		hours = (t1 - t0).total_seconds() / 3600.0
		if hours <= 0 or hours * 60 > max_gap_minutes:
			continue
		total += (max(v0, 0.0) + max(v1, 0.0)) / 2.0 * hours / per_hours
	return total


def consumption(
	mode: str,
	readings: list[tuple[datetime, float]],
	*,
	rollover: float | None = None,
	max_gap_minutes: float = 60,
	per_hours: float = 1.0,
) -> float:
	if mode == "Totalizer":
		return totalizer_consumption(readings, rollover)
	if mode == "Rate":
		return rate_consumption(readings, max_gap_minutes, per_hours)
	raise ValueError(f"meter mode must be one of {', '.join(METER_MODES)}")


def run_hours(
	readings: list[tuple[datetime, float]], since: datetime, until: datetime, max_gap_minutes: float = 60
) -> float:
	"""Hours a binary run-status point read on (non-zero) in [since, until).

	Each reading holds until the next one, or for at most max_gap_minutes when the next is late or
	missing: a point that stops reporting stops counting hours. The reading in force at `since` is
	the last one before it, when it is recent enough."""
	if until <= since:
		return 0.0
	gap = timedelta(minutes=max_gap_minutes)
	ordered = sorted(readings)
	total = 0.0
	for index, (at, value) in enumerate(ordered):
		end = ordered[index + 1][0] if index + 1 < len(ordered) else until
		end = min(end, at + gap, until)
		start = max(at, since)
		if value and end > start:
			total += (end - start).total_seconds()
	return total / 3600.0


def period_start(at: datetime | date, period: str) -> date:
	"""The first day of the Day, Week (Monday) or Month that `at` falls in."""
	day = at.date() if isinstance(at, datetime) else at
	if period == "Day":
		return day
	if period == "Week":
		return day - timedelta(days=day.weekday())
	if period == "Month":
		return day.replace(day=1)
	raise ValueError("period must be Day, Week or Month")


def consumption_by_period(
	mode: str, readings: list[tuple[datetime, float]], period: str, **options
) -> dict[date, float]:
	"""Consumption per period. A totaliser's increase between two readings in different periods is
	charged to the later one; a rate's trapezoid likewise."""
	out: dict[date, float] = {}
	ordered = sorted(readings)
	for pair in pairwise(ordered):
		bucket = period_start(pair[1][0], period)
		out[bucket] = out.get(bucket, 0.0) + consumption(mode, list(pair), **options)
	return out


def intensity(consumed: float, good_units: float) -> float | None:
	"""Consumption per good unit made (an ISO 50001 energy performance indicator)."""
	return consumed / good_units if good_units else None


# Findings


def alarm_finding(alarm: dict) -> dict:
	"""The Agent Suggestion for a newly raised building alarm.

	alarm: name, point, point_title, facility_asset, system, zone, condition, priority, value, limit,
	unit, raised_at and, for hazardous material storage, hazard_assessment."""
	hazmat = alarm.get("system") == "Hazardous Material Storage"
	priority = alarm.get("priority") or "Medium"
	severity = (
		"Critical" if hazmat and priority in ("Critical", "High") else SEVERITY.get(priority, "Warning")
	)
	what = alarm.get("point_title") or alarm.get("point")
	unit = f" {alarm['unit']}" if alarm.get("unit") else ""
	if alarm.get("condition") == STALE:
		detail = f"{what} has stopped reporting (last reading {alarm.get('last_value_at') or 'unknown'})."
		ask = "Check the controller, its network and the gateway; until then FoaMES cannot see this system."
	else:
		detail = (
			f"{what} reads {alarm.get('value')}{unit}, past its {alarm.get('condition')} limit "
			f"of {alarm.get('limit')}{unit}."
		)
		ask = "Check the equipment and acknowledge the alarm in FoaMES once someone is on it."
	if hazmat:
		ask += (
			" This is hazardous material storage: follow its hazard assessment"
			f"{' ' + alarm['hazard_assessment'] if alarm.get('hazard_assessment') else ''} before anyone goes in."
		)
	return {
		"rule_key": f"bms-alarm:{alarm['name']}:{alarm.get('condition')}",
		"category": "Safety" if hazmat else "Facility",
		"severity": severity,
		"title": f"{alarm.get('facility_asset')}: {alarm.get('condition')} on {what}",
		"suggestion": f"{detail} {ask}",
		"reference_doctype": "Building Alarm",
		"reference_name": alarm["name"],
		"evidence": {
			"point": alarm.get("point"),
			"facility_asset": alarm.get("facility_asset"),
			"system": alarm.get("system"),
			"zone": alarm.get("zone"),
			"condition": alarm.get("condition"),
			"priority": priority,
			"value": alarm.get("value"),
			"limit": alarm.get("limit"),
			"raised_at": str(alarm.get("raised_at")),
			"hazard_assessment": alarm.get("hazard_assessment"),
		},
	}


def unacknowledged_findings(alarms: list[dict], now: datetime, minutes: int = 30) -> list[dict]:
	"""Critical and High alarms still active and unacknowledged after `minutes`."""
	out = []
	for alarm in alarms:
		if alarm.get("status") != "Active" or alarm.get("priority") not in ("Critical", "High"):
			continue
		raised = alarm.get("raised_at")
		if not raised or now - raised < timedelta(minutes=minutes):
			continue
		text = (
			f"{alarm.get('priority')} alarm {alarm['name']} ({alarm.get('condition')} on "
			f"{alarm.get('point')}, {alarm.get('facility_asset')}) has been active since "
			f"{raised} and nobody has acknowledged it. Escalate it to facilities."
		)
		out.append(
			{
				"rule_key": f"bms-unacknowledged:{alarm['name']}",
				"category": "Facility",
				"severity": "Critical",
				"title": f"Building alarm {alarm['name']} unacknowledged for {minutes}+ minutes",
				"suggestion": text,
				"reference_doctype": "Building Alarm",
				"reference_name": alarm["name"],
				"evidence": {"raised_at": str(raised), "priority": alarm.get("priority")},
			}
		)
	return out


def hazmat_findings(assets: list[dict]) -> list[dict]:
	"""Hazardous material storage with no active hazard assessment, or with no point watching it."""
	out = []
	for asset in assets:
		if asset.get("system") != "Hazardous Material Storage" or asset.get("out_of_service"):
			continue
		if not asset.get("hazard_assessment_active"):
			text = (
				f"Hazardous material storage {asset['name']} is not linked to an active Hazard "
				"Assessment. Link the assessment that covers what is stored there, so an alarm on "
				"it points people at the right controls."
			)
			out.append(
				{
					"rule_key": f"bms-hazmat-no-assessment:{asset['name']}",
					"category": "Safety",
					"severity": "Warning",
					"title": f"{asset['name']} has no active hazard assessment",
					"suggestion": text,
					"reference_doctype": "Facility Asset",
					"reference_name": asset["name"],
					"evidence": {"hazard_assessment": asset.get("hazard_assessment")},
				}
			)
		if not asset.get("point_count"):
			text = (
				f"Hazardous material storage {asset['name']} has no Building Point. Storage rooms "
				"and cabinets usually report temperature, ventilation status and leak or gas "
				"detection; add the ones it has so FoaMES can watch them."
			)
			out.append(
				{
					"rule_key": f"bms-hazmat-unmonitored:{asset['name']}",
					"category": "Safety",
					"severity": "Info",
					"title": f"{asset['name']} has no monitored points",
					"suggestion": text,
					"reference_doctype": "Facility Asset",
					"reference_name": asset["name"],
					"evidence": {},
				}
			)
	return out
