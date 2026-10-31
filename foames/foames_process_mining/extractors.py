# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Event-log extraction from a FoaMES site.

Three kinds of source feed a log:

- Built-in extractors over FoaMES records: machine state changes and downtime.
- Field-mapped sources: any DocType on the site, described by an `Event Log Source` record that
  names the case, activity, timestamp and resource fields. This is how ERP records such as job
  cards or work orders are mined without the core linking to them: the DocType is named as text
  and resolved at run time, and the source is skipped when the DocType is not installed.
- Hook extractors: other apps register dotted paths under `foames_process_event_extractors`,
  each called with (since, until) and returning an iterable of Event.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime

import frappe
from frappe.utils import get_datetime

from foames.foames_process_mining.eventlog import COMPLETE, START, Event, EventLog

BUILT_IN = ("Machine States", "Downtime")


def build_event_log(
	since=None, until=None, sources: Iterable[str] | None = None, name: str = "", built_in: bool = True
) -> EventLog:
	"""Every event from the enabled sources in the window. `sources` limits to the named Event Log
	Source records (plus the built-in extractors when `built_in` is true)."""
	since, until = _window(since, until)
	events: list[Event] = []
	if built_in:
		events.extend(machine_state_events(since, until))
		events.extend(downtime_events(since, until))
	filters = {"enabled": 1}
	if sources:
		filters["name"] = ("in", list(sources))
	for source in frappe.get_all("Event Log Source", filters, pluck="name"):
		events.extend(frappe.get_doc("Event Log Source", source).extract(since, until))
	for extractor in frappe.get_hooks("foames_process_event_extractors") or []:
		events.extend(frappe.get_attr(extractor)(since, until))
	log = EventLog(events, name=name or "FoaMES event log")
	if since:
		log.attributes["since"] = since.isoformat()
	if until:
		log.attributes["until"] = until.isoformat()
	return log


# Built-in extractors --------------------------------------------------------------------------


def machine_state_events(since: datetime | None, until: datetime | None) -> Iterator[Event]:
	"""One trace per machine per calendar day; each State event is an activity named by the
	state it entered. Alarms are their own activity. The machine is an OCEL object."""
	filters = [["event_type", "in", ("State", "Alarm")], ["processed", "=", 1]]
	filters += _window_filters("timestamp", since, until)
	rows = frappe.get_all(
		"Machine Event",
		filters,
		["name", "machine", "event_type", "state", "timestamp", "source"],
		order_by="timestamp asc",
	)
	for row in rows:
		timestamp = get_datetime(row.timestamp)
		activity = row.state if row.event_type == "State" else "Alarm"
		if not activity:
			continue
		yield Event(
			case_id=f"{row.machine}:{timestamp.date().isoformat()}",
			activity=activity,
			timestamp=timestamp,
			resource=row.machine,
			attributes={"source": row.source, "machine_event": row.name},
			objects={"machine": [row.machine]},
		)


def downtime_events(since: datetime | None, until: datetime | None) -> Iterator[Event]:
	"""Each Downtime Record is a case: Down (start) and, when closed, Down (complete) with the
	reason as an attribute. Lets downtime be mined for duration by reason and by machine."""
	# A downtime that overlaps the window is kept whole, so its duration can still be measured.
	filters, or_filters = _overlap_filters("start_time", "end_time", since, until)
	rows = frappe.get_all(
		"Downtime Record",
		filters,
		["name", "machine", "reason", "status", "start_time", "end_time", "source"],
		or_filters=or_filters,
		order_by="start_time asc",
	)
	for row in rows:
		attributes = {"reason": row.reason, "status": row.status, "source": row.source}
		objects = {"machine": [row.machine], "downtime": [row.name]}
		yield Event(row.name, "Down", get_datetime(row.start_time), row.machine, START, attributes, objects)
		if row.end_time:
			yield Event(
				row.name, "Down", get_datetime(row.end_time), row.machine, COMPLETE, attributes, objects
			)


# Field-mapped sources ------------------------------------------------------------------------


def extract_from_mapping(mapping: dict, since: datetime | None, until: datetime | None) -> Iterator[Event]:
	"""Events from any DocType described by a field map.

	mapping keys: source_doctype, case_field, activity_field or fixed_activity, timestamp_field,
	end_timestamp_field (optional; makes start/complete pairs), resource_field (optional),
	filters (JSON dict or list), attribute_fields (comma-separated), object_fields (comma-separated
	`type=field` or `field`).

	The query runs with the current user's permissions (frappe.get_list), so a source can only
	yield records and fields that user may read. With an end field, a record whose activity
	overlaps the window is kept whole, start and complete, so durations stay measurable.
	"""
	doctype = mapping["source_doctype"]
	if not frappe.db.exists("DocType", doctype):
		return
	if not frappe.has_permission(doctype, "read"):
		raise frappe.PermissionError(frappe._("Not permitted to read {0}").format(doctype))
	meta = frappe.get_meta(doctype)
	fields = {"name", mapping["case_field"], mapping["timestamp_field"]}
	for key in ("activity_field", "end_timestamp_field", "resource_field"):
		if mapping.get(key):
			fields.add(mapping[key])
	attribute_fields = _split(mapping.get("attribute_fields"))
	object_fields = [_object_field(spec) for spec in _split(mapping.get("object_fields"))]
	fields.update(attribute_fields)
	fields.update(f for _, f in object_fields)
	valid = {df.fieldname for df in meta.fields} | {"name", "owner", "modified_by", "creation", "modified"}
	unknown = sorted(f for f in fields if f not in valid)
	if unknown:
		raise frappe.ValidationError(f"{doctype} has no field {', '.join(unknown)}")

	filters = _parse_filters(mapping.get("filters"))
	if isinstance(filters, dict):
		filters = [[doctype, key, "=", value] for key, value in filters.items()]
	else:
		filters = list(filters)
	or_filters = []
	if mapping.get("end_timestamp_field"):
		window, or_filters = _overlap_filters(
			mapping["timestamp_field"], mapping["end_timestamp_field"], since, until
		)
		filters += window
	else:
		filters += _window_filters(mapping["timestamp_field"], since, until)

	rows = frappe.get_list(
		doctype,
		filters=filters,
		or_filters=or_filters,
		fields=list(fields),
		order_by=f"{mapping['timestamp_field']} asc",
	)
	for row in rows:
		case_id = row.get(mapping["case_field"])
		started = row.get(mapping["timestamp_field"])
		if not case_id or not started:
			continue
		activity = (
			row.get(mapping["activity_field"])
			if mapping.get("activity_field")
			else mapping.get("fixed_activity")
		)
		if not activity:
			continue
		resource = row.get(mapping["resource_field"]) if mapping.get("resource_field") else None
		attributes = {f: row.get(f) for f in attribute_fields}
		attributes["source_doctype"], attributes["source_name"] = doctype, row.name
		objects = {t: [str(row.get(f))] for t, f in object_fields if row.get(f)}
		ended = row.get(mapping["end_timestamp_field"]) if mapping.get("end_timestamp_field") else None
		if ended:
			yield Event(
				str(case_id), str(activity), get_datetime(started), resource, START, attributes, objects
			)
			yield Event(
				str(case_id), str(activity), get_datetime(ended), resource, COMPLETE, attributes, objects
			)
		else:
			yield Event(
				str(case_id), str(activity), get_datetime(started), resource, COMPLETE, attributes, objects
			)


# Helpers ------------------------------------------------------------------------------------


def _window(since, until) -> tuple[datetime | None, datetime | None]:
	since = get_datetime(since) if since else None
	until = get_datetime(until) if until else None
	if since and until and until <= since:
		frappe.throw(frappe._("The window's end must be after its start"))
	return since, until


def _window_filters(fieldname: str, since, until) -> list[list]:
	"""since <= field < until: the upper bound is exclusive, so adjacent windows never share an event."""
	filters = []
	if since:
		filters.append([fieldname, ">=", since])
	if until:
		filters.append([fieldname, "<", until])
	return filters


def _overlap_filters(start_field: str, end_field: str, since, until) -> tuple[list[list], list[list]]:
	"""(filters, or_filters) for records whose [start, end] overlaps the window; an open record with
	no end yet counts as ongoing."""
	filters, or_filters = [], []
	if until:
		filters.append([start_field, "<", until])
	if since:
		or_filters = [[end_field, ">=", since], [end_field, "is", "not set"]]
	return filters, or_filters


def _split(text) -> list[str]:
	return [part.strip() for part in (text or "").split(",") if part.strip()]


def _object_field(spec: str) -> tuple[str, str]:
	if "=" in spec:
		object_type, fieldname = spec.split("=", 1)
		return object_type.strip(), fieldname.strip()
	return spec, spec


def _parse_filters(raw):
	if not raw:
		return {}
	if isinstance(raw, dict | list):
		return raw
	try:
		return json.loads(raw)
	except ValueError:
		frappe.throw(frappe._("Filters must be a JSON object or list"))
