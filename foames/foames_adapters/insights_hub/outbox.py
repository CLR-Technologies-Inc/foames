# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Outbox rules for writes to Insights Hub: what each operation sends, how a write is made
idempotent, and when a failed write is retried.

Two operations are defined, both on the platform APIs Opcenter Intelligence reads from:

- **Time Series Write** puts records on an aspect (property set) of an asset. The platform keys a
  record on its `_time`, so writing the same record again overwrites it: the write is idempotent by
  nature and a retry after an unclear answer simply sends it again.
- **Event** creates an event on an asset. An event has no natural key, so the posting writes a
  marker derived from its idempotency key into the event's `correlationId`. When a send ends without
  a clear answer (a timeout, a dropped connection, a 5xx), the next attempt first searches the asset's
  events around the event's timestamp for that marker and records the existing event instead of
  creating a second one.

This module has no Frappe imports; the Insights Hub Outbox DocType applies these rules.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from foames.foames_adapters.insights_hub.rest import InsightsHubError, RestClient, json_filter

MARKER_PREFIX = "FOAMES-"
BASE_DELAY_SECONDS = 60
MAX_DELAY_SECONDS = 6 * 3600
MAX_ATTEMPTS = 12

TIME_SERIES = "Time Series Write"
EVENT = "Event"

TIME_SERIES_SERVICE = "iottimeseries/v3"
EVENT_SERVICE = "eventmanagement/v3"
# The platform's built-in event type, which every tenant has.
STANDARD_EVENT_TYPE = "com.siemens.mindsphere.eventmgmt.event.type.MindSphereStandardEvent"
# Severities of the standard event type.
SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFORMATION = 20, 30, 40


@dataclass
class Operation:
	label: str
	service: str
	required: tuple[str, ...]  # payload fields a posting cannot do without
	idempotent: bool  # whether sending the same payload twice leaves one record


OPERATIONS: dict[str, Operation] = {
	TIME_SERIES: Operation(
		label=TIME_SERIES,
		service=TIME_SERIES_SERVICE,
		required=("entityId", "propertySetName", "data"),
		idempotent=True,
	),
	EVENT: Operation(
		label=EVENT,
		service=EVENT_SERVICE,
		required=("entityId", "timestamp"),
		idempotent=False,
	),
}


def operation(name: str) -> Operation:
	if name in OPERATIONS:
		return OPERATIONS[name]
	raise KeyError(name)


def operation_names() -> list[str]:
	return list(OPERATIONS)


def marker(idempotency_key: str) -> str:
	"""A 23-character marker written into an event's correlationId."""
	return MARKER_PREFIX + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16].upper()


def prepare(operation: Operation, payload: dict, idempotency_key: str) -> dict:
	"""The payload as sent: checked, copied, and for an event carrying the marker."""
	missing = [name for name in operation.required if not payload.get(name)]
	if missing:
		raise ValueError(f"{operation.label} needs {', '.join(missing)}")
	prepared = dict(payload)
	if operation.label == TIME_SERIES:
		data = prepared["data"]
		if not isinstance(data, list) or not all(isinstance(r, dict) and r.get("_time") for r in data):
			raise ValueError("Time Series Write needs data: a list of records that each carry _time")
	elif operation.label == EVENT:
		prepared.setdefault("typeId", STANDARD_EVENT_TYPE)
		prepared["correlationId"] = marker(idempotency_key)
	return prepared


def document_id(operation: Operation, payload: dict, answer) -> str:
	"""What identifies the write in Insights Hub afterwards: the event's id, or for time series
	the asset, aspect and last record time (the platform returns nothing for a time series write)."""
	if operation.label == EVENT:
		return str((answer or {}).get("id") or "")
	times = sorted(str(record.get("_time")) for record in payload.get("data", []))
	return f"{payload.get('entityId')}/{payload.get('propertySetName')}@{times[-1] if times else ''}"


def time_series_path(payload: dict) -> str:
	return f"{TIME_SERIES_SERVICE}/timeseries/{payload['entityId']}/{payload['propertySetName']}"


def find_existing(client: RestClient, payload: dict) -> dict | None:
	"""The event an earlier attempt of this posting created, if Insights Hub has one.

	Events are searched on the asset and type within a minute of the event's timestamp and matched
	on the correlation id, because that is what the event filter is sure to support."""
	at = parse_time(payload["timestamp"])
	window = (at - timedelta(minutes=1), at + timedelta(minutes=1)) if at else None
	filters = {"entityId": payload["entityId"], "typeId": payload.get("typeId", STANDARD_EVENT_TYPE)}
	if window:
		filters["timestamp"] = {"between": f"[{iso_utc(window[0])},{iso_utc(window[1])}]"}
	events = client.get_page(f"{EVENT_SERVICE}/events", {"filter": json_filter(filters)}, size=50)
	for event in events:
		if event.get("correlationId") == payload.get("correlationId"):
			return event
	return None


@dataclass
class Outcome:
	status: str  # Posted, Retry, Unknown or Failed
	document: str = ""
	error: str = ""
	details: list | None = None
	response: dict | None = None


def send(client: RestClient, operation: Operation, payload: dict, verify_first: bool) -> Outcome:
	"""Send once. With `verify_first`, look for an earlier posting with the same marker first (an
	idempotent write is simply sent again)."""
	try:
		if operation.label == TIME_SERIES:
			client.write("PUT", time_series_path(payload), payload["data"], idempotent=True)
			return Outcome("Posted", document_id(operation, payload, None))
		if verify_first:
			existing = find_existing(client, payload)
			if existing:
				return Outcome("Posted", document_id(operation, payload, existing), response=existing)
		created = client.write("POST", f"{EVENT_SERVICE}/events", payload)
		return Outcome("Posted", document_id(operation, payload, created), response=created)
	except InsightsHubError as e:
		if not e.transient:
			return Outcome("Failed", error=str(e), details=e.details)
		if operation.idempotent:
			# Sending it again is harmless, so there is nothing to verify.
			return Outcome("Retry", error=str(e), details=e.details)
		return Outcome(
			"Unknown" if e.maybe_applied or verify_first else "Retry", error=str(e), details=e.details
		)


def retry_delay(attempts: int) -> int:
	"""Seconds to wait after the given number of failed attempts: 1, 2, 4 ... minutes, capped at 6 h."""
	return min(BASE_DELAY_SECONDS * 2 ** max(attempts - 1, 0), MAX_DELAY_SECONDS)


def give_up(attempts: int) -> bool:
	return attempts >= MAX_ATTEMPTS


# Time


def iso_utc(moment: datetime) -> str:
	"""The platform's timestamp form: UTC, milliseconds, `Z`. A naive datetime is taken as UTC."""
	if moment.tzinfo is None:
		moment = moment.replace(tzinfo=timezone.utc)
	moment = moment.astimezone(timezone.utc)
	return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def parse_time(value) -> datetime | None:
	"""A platform timestamp back into an aware datetime, or None when it is not one."""
	if isinstance(value, datetime):
		return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
	if not value:
		return None
	text = str(value).strip()
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	try:
		parsed = datetime.fromisoformat(text)
	except ValueError:
		return None
	return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
