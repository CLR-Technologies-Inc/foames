# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""XES (IEEE 1849-2016) export and import.

XES is the interchange format every process-mining tool reads (ProM, PM4Py, Celonis, Disco). The
export writes the concept, time, lifecycle and organizational extensions; other attributes become
string attributes on the event. The import reads the same, and tolerates logs from other tools
that use different attribute keys for the case id.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from foames.foames_process_mining.eventlog import COMPLETE, Event, EventLog, parse_timestamp

EXTENSIONS = (
	("Concept", "concept", "http://www.xes-standard.org/concept.xesext"),
	("Time", "time", "http://www.xes-standard.org/time.xesext"),
	("Lifecycle", "lifecycle", "http://www.xes-standard.org/lifecycle.xesext"),
	("Organizational", "org", "http://www.xes-standard.org/org.xesext"),
)


def to_xes(log: EventLog) -> str:
	root = ET.Element(
		"log",
		{
			"xes.version": "1849-2016",
			"xes.features": "nested-attributes",
			"xmlns": "http://www.xes-standard.org/",
		},
	)
	for name, prefix, uri in EXTENSIONS:
		ET.SubElement(root, "extension", {"name": name, "prefix": prefix, "uri": uri})
	ET.SubElement(root, "classifier", {"name": "Activity", "keys": "concept:name"})
	ET.SubElement(
		root, "classifier", {"name": "Activity and lifecycle", "keys": "concept:name lifecycle:transition"}
	)
	_attribute(root, "string", "concept:name", log.name or "FoaMES event log")
	_attribute(root, "string", "lifecycle:model", "standard")
	for key, value in log.attributes.items():
		_attribute(root, "string", str(key), str(value))

	for case_id, events in log.traces().items():
		trace = ET.SubElement(root, "trace")
		_attribute(trace, "string", "concept:name", case_id)
		for event in events:
			element = ET.SubElement(trace, "event")
			_attribute(element, "string", "concept:name", event.activity)
			_attribute(element, "date", "time:timestamp", _iso(event.timestamp))
			_attribute(element, "string", "lifecycle:transition", event.lifecycle or COMPLETE)
			if event.resource:
				_attribute(element, "string", "org:resource", event.resource)
			for key, value in event.attributes.items():
				_typed_attribute(element, str(key), value)
			for object_type, ids in event.objects.items():
				# A JSON list, so an id that contains a comma survives the round trip.
				_attribute(element, "string", f"foames:object:{object_type}", json.dumps(list(ids)))

	ET.indent(root)
	return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def from_xes(text: str | bytes, name: str = "") -> EventLog:
	root = ET.fromstring(text)
	ns = _namespace(root)
	events: list[Event] = []
	for trace in root.iter(f"{ns}trace"):
		case_id = _get(trace, ns, "concept:name") or _get(trace, ns, "case:id") or f"case-{len(events)}"
		for element in trace.findall(f"{ns}event"):
			attributes, objects = {}, {}
			activity = resource = lifecycle = timestamp = None
			for child in element:
				key = child.get("key")
				value = child.get("value")
				if key == "concept:name":
					activity = value
				elif key == "time:timestamp":
					timestamp = parse_timestamp(value)
				elif key == "lifecycle:transition":
					lifecycle = value
				elif key == "org:resource":
					resource = value
				elif key and key.startswith("foames:object:"):
					objects[key.removeprefix("foames:object:")] = _object_ids(value)
				elif key:
					attributes[key] = _typed_value(_local_name(child.tag), value)
			if activity and timestamp:
				events.append(
					Event(case_id, activity, timestamp, resource, lifecycle or COMPLETE, attributes, objects)
				)
	return EventLog(events, name=name or _get(root, ns, "concept:name") or "")


def _attribute(parent, kind: str, key: str, value: str):
	ET.SubElement(parent, kind, {"key": key, "value": value})


def _typed_attribute(parent, key: str, value):
	if isinstance(value, bool):
		_attribute(parent, "boolean", key, "true" if value else "false")
	elif isinstance(value, int):
		_attribute(parent, "int", key, str(value))
	elif isinstance(value, float):
		_attribute(parent, "float", key, repr(value))
	elif isinstance(value, datetime):
		_attribute(parent, "date", key, _iso(value))
	else:
		_attribute(parent, "string", key, "" if value is None else str(value))


def _iso(value: datetime) -> str:
	if value.tzinfo is None:
		value = value.replace(tzinfo=timezone.utc)
	return value.isoformat()


def _object_ids(value: str | None) -> list[str]:
	text = value or ""
	if text.startswith("["):
		try:
			return [str(v) for v in json.loads(text)]
		except ValueError:
			pass
	return [v for v in text.split(",") if v]  # logs written before the JSON encoding


def _typed_value(kind: str, value: str | None):
	"""The Python value of an XES attribute from its element type."""
	if value is None:
		return None
	try:
		if kind == "int":
			return int(value)
		if kind == "float":
			return float(value)
		if kind == "boolean":
			return value.strip().lower() == "true"
		if kind == "date":
			return parse_timestamp(value)
	except ValueError:
		return value
	return value


def _local_name(tag: str) -> str:
	return tag[tag.index("}") + 1 :] if tag.startswith("{") else tag


def _namespace(root) -> str:
	tag = root.tag
	return tag[: tag.index("}") + 1] if tag.startswith("{") else ""


def _get(element, ns: str, key: str) -> str | None:
	for child in element:
		if child.tag in (f"{ns}string", "string") and child.get("key") == key:
			return child.get("value")
	return None
