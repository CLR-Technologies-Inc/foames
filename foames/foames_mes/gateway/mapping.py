# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Turn raw gateway messages into Machine Event dicts. No Frappe dependency.

Both the MQTT and OPC UA gateways, and the webhook, end up calling `normalise_event`, so every
path to the database goes through one validation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

EVENT_TYPES = ("State", "Count", "Measurement", "Alarm", "Message")
MACHINE_STATES = ("Unknown", "Running", "Idle", "Down", "Setup")

# Lower-case aliases that PLC programs commonly send.
STATE_ALIASES = {
	"run": "Running",
	"running": "Running",
	"auto": "Running",
	"producing": "Running",
	"idle": "Idle",
	"ready": "Idle",
	"waiting": "Idle",
	"starved": "Idle",
	"blocked": "Idle",
	"down": "Down",
	"fault": "Down",
	"faulted": "Down",
	"stopped": "Down",
	"alarm": "Down",
	"setup": "Setup",
	"changeover": "Setup",
	"unknown": "Unknown",
}


class EventError(ValueError):
	pass


def normalise_event(raw: dict, source: str = "Webhook") -> dict:
	"""Validate and standardise one event. Raises EventError with a plain reason."""
	if not isinstance(raw, dict):
		raise EventError("event must be an object")
	machine = raw.get("machine") or raw.get("source_id")
	if not machine:
		raise EventError("event needs a machine (its source id)")
	event_type = str(raw.get("type") or raw.get("event_type") or "").strip().title()
	if event_type not in EVENT_TYPES:
		raise EventError(f"event type must be one of {', '.join(EVENT_TYPES)}")
	event = {
		"source_id": str(machine),
		"event_type": event_type,
		"timestamp": parse_timestamp(raw.get("timestamp") or raw.get("ts")),
		"source": source,
		"event_key": str(raw["id"]) if raw.get("id") else None,
		"text": raw.get("text") or raw.get("message"),
		"payload": raw,
	}
	if event_type == "State":
		event["state"] = normalise_state(raw.get("state") or raw.get("value"))
	elif event_type == "Count":
		event["counter_name"] = str(raw.get("counter") or raw.get("name") or "good").lower()
		event["counter_value"] = _number(raw.get("value"), "counter value")
	elif event_type == "Measurement":
		event["measurement_name"] = str(raw.get("name") or raw.get("measurement") or "").strip()
		if not event["measurement_name"]:
			raise EventError("a measurement needs a name")
		event["value"] = _number(raw.get("value"), "measurement value")
	elif event_type == "Alarm":
		event["value"] = _number(raw.get("value") or raw.get("code") or 0, "alarm code")
		event["text"] = event["text"] or str(raw.get("code") or "")
	return event


def normalise_state(value) -> str:
	if value is None:
		raise EventError("a state event needs a state")
	text = str(value).strip()
	if text in MACHINE_STATES:
		return text
	state = STATE_ALIASES.get(text.lower())
	if not state:
		raise EventError(f"unknown machine state {text!r}")
	return state


def parse_timestamp(value) -> datetime:
	"""ISO 8601 or Unix seconds, always returned as a naive UTC datetime."""
	if value is None:
		return datetime.now(timezone.utc).replace(tzinfo=None)
	if isinstance(value, int | float):
		return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
	text = str(value).strip()
	try:
		parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
	except ValueError:
		raise EventError(f"cannot read timestamp {text!r}")
	if parsed.tzinfo is not None:
		parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
	return parsed


def parse_topic(topic: str, prefix: str) -> tuple[str, str] | None:
	"""`<prefix>/<source id>/<event type>` -> (source id, event type), else None."""
	parts = topic.split("/")
	prefix_parts = [p for p in prefix.split("/") if p]
	if parts[: len(prefix_parts)] != prefix_parts or len(parts) < len(prefix_parts) + 2:
		return None
	source_id = "/".join(parts[len(prefix_parts) : -1])
	return source_id, parts[-1]


def mqtt_message_to_raw(topic: str, payload: bytes | str, prefix: str) -> dict:
	parsed = parse_topic(topic, prefix)
	if not parsed:
		raise EventError(f"topic {topic!r} is not under {prefix!r}/<machine>/<type>")
	source_id, event_type = parsed
	if isinstance(payload, bytes):
		payload = payload.decode("utf-8", errors="replace")
	try:
		body = json.loads(payload)
	except ValueError:
		body = {"value": payload}
	if not isinstance(body, dict):
		body = {"value": body}
	body.setdefault("machine", source_id)
	body.setdefault("type", event_type)
	return body


def _number(value, label) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		raise EventError(f"{label} must be a number, got {value!r}")
