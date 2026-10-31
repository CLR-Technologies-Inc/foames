# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OCEL 2.0 (object-centric event log) JSON export and import.

A manufacturing event rarely has one case: a count on a press belongs to the machine, the order
being run and the lot it fills. OCEL keeps every object an event touched, so the same log can be
flattened on any of them. The JSON here follows the OCEL 2.0 standard (ocel-standard.org):
objectTypes, eventTypes, objects, events, with events holding relationships to objects.
"""

from __future__ import annotations

import json

from foames.foames_process_mining.eventlog import COMPLETE, Event, EventLog, parse_timestamp

CASE_OBJECT_TYPE = "case"


def to_ocel(log: EventLog, case_object_type: str = CASE_OBJECT_TYPE) -> dict:
	"""The log as an OCEL 2.0 dict. The case id becomes an object of `case_object_type` so a log
	with no explicit objects is still a valid object-centric log."""
	object_types: dict[str, dict] = {}
	event_types: dict[str, dict] = {}
	objects: dict[tuple[str, str], dict] = {}
	events = []

	for index, event in enumerate(log, start=1):
		touched = {case_object_type: [event.case_id]}
		for object_type, ids in event.objects.items():
			touched.setdefault(object_type, []).extend(ids)
		relationships = []
		for object_type, ids in touched.items():
			object_types.setdefault(object_type, {"name": object_type, "attributes": []})
			for object_id in dict.fromkeys(ids):
				objects.setdefault(
					(object_type, object_id), {"id": object_id, "type": object_type, "attributes": []}
				)
				relationships.append({"objectId": object_id, "qualifier": object_type})
		activity_type = event_types.setdefault(event.activity, {"name": event.activity, "attributes": []})
		attributes = [{"name": "lifecycle", "value": event.lifecycle or COMPLETE}]
		if event.resource:
			attributes.append({"name": "resource", "value": event.resource})
		for key, value in event.attributes.items():
			attributes.append(
				{"name": str(key), "value": value if isinstance(value, int | float | bool) else str(value)}
			)
		_register_attributes(activity_type, attributes)
		events.append(
			{
				"id": f"e{index}",
				"type": event.activity,
				"time": event.timestamp.isoformat(),
				"attributes": attributes,
				"relationships": relationships,
			}
		)

	_register_attributes(event_types.setdefault("__all__", {"name": "__all__", "attributes": []}), [])
	event_types.pop("__all__")
	return {
		"objectTypes": list(object_types.values()),
		"eventTypes": list(event_types.values()),
		"objects": list(objects.values()),
		"events": events,
	}


def to_ocel_json(log: EventLog, **kwargs) -> str:
	return json.dumps(to_ocel(log, **kwargs), indent=1, default=str)


def from_ocel(data: dict | str | bytes, case_object_type: str = CASE_OBJECT_TYPE, name: str = "") -> EventLog:
	"""Flatten an OCEL 2.0 log on `case_object_type`. An event related to several objects of
	that type appears once per object, which is the standard flattening."""
	if isinstance(data, str | bytes):
		data = json.loads(data)
	type_of = {obj["id"]: obj["type"] for obj in data.get("objects", [])}
	events: list[Event] = []
	for raw in data.get("events", []):
		attributes = {a["name"]: a["value"] for a in raw.get("attributes", [])}
		lifecycle = attributes.pop("lifecycle", COMPLETE)
		resource = attributes.pop("resource", None)
		objects: dict[str, list[str]] = {}
		for rel in raw.get("relationships", []):
			object_type = type_of.get(rel["objectId"], rel.get("qualifier", "object"))
			objects.setdefault(object_type, []).append(rel["objectId"])
		cases = objects.pop(case_object_type, None) or [raw["id"]]
		for case_id in cases:
			events.append(
				Event(
					case_id,
					raw["type"],
					parse_timestamp(raw["time"]),
					resource,
					lifecycle,
					dict(attributes),
					objects,
				)
			)
	return EventLog(events, name=name)


def _register_attributes(event_type: dict, attributes: list[dict]):
	known = {a["name"] for a in event_type["attributes"]}
	for attribute in attributes:
		if attribute["name"] not in known:
			value = attribute["value"]
			kind = (
				"boolean"
				if isinstance(value, bool)
				else "integer"
				if isinstance(value, int)
				else "float"
				if isinstance(value, float)
				else "string"
			)
			event_type["attributes"].append({"name": attribute["name"], "type": kind})
			known.add(attribute["name"])
