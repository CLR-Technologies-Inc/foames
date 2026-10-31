# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The event log: the one data structure every process-mining analysis starts from.

An event is something that happened to a case (a production order, a lot, a machine-day) at a
time, named by its activity. A trace is a case's events in time order. Lifecycle transitions
(start, complete) follow the XES standard lifecycle extension, so an activity with a duration is
two events. Objects are the OCEL view of the same event: every entity it touched, by type.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone

START, COMPLETE = "start", "complete"


@dataclass(frozen=True)
class Event:
	case_id: str
	activity: str
	timestamp: datetime
	resource: str | None = None
	lifecycle: str = COMPLETE
	attributes: dict = field(default_factory=dict, compare=False, hash=False)
	# OCEL objects touched by this event: {"machine": ["press-1"], "work_order": ["WO-1"]}
	objects: dict[str, list[str]] = field(default_factory=dict, compare=False, hash=False)

	def __post_init__(self):
		if not self.case_id:
			raise ValueError("an event needs a case id")
		if not self.activity:
			raise ValueError("an event needs an activity")
		if not isinstance(self.timestamp, datetime):
			raise TypeError("timestamp must be a datetime")


class EventLog:
	"""An ordered collection of events with trace, variant and attribute views."""

	def __init__(self, events: Iterable[Event] = (), name: str = "", attributes: dict | None = None):
		self.name = name
		self.attributes = dict(attributes or {})
		self._events: list[Event] = sorted(events, key=_sort_key)

	# Container protocol ---------------------------------------------------------------------

	def __len__(self) -> int:
		return len(self._events)

	def __iter__(self) -> Iterator[Event]:
		return iter(self._events)

	def __bool__(self) -> bool:
		return bool(self._events)

	@property
	def events(self) -> list[Event]:
		return list(self._events)

	def add(self, event: Event) -> None:
		self._events.append(event)
		self._events.sort(key=_sort_key)

	def extend(self, events: Iterable[Event]) -> None:
		self._events.extend(events)
		self._events.sort(key=_sort_key)

	# Views ----------------------------------------------------------------------------------

	def traces(self) -> dict[str, list[Event]]:
		"""Events grouped by case, each in time order. Dict order is first appearance."""
		traces: dict[str, list[Event]] = defaultdict(list)
		for event in self._events:
			traces[event.case_id].append(event)
		return dict(traces)

	def case_ids(self) -> list[str]:
		return list(self.traces())

	def activities(self) -> list[str]:
		"""Distinct activity names, in first-appearance order."""
		return list(dict.fromkeys(e.activity for e in self._events))

	def resources(self) -> list[str]:
		return list(dict.fromkeys(e.resource for e in self._events if e.resource))

	def object_types(self) -> list[str]:
		seen: dict[str, None] = {}
		for event in self._events:
			for object_type in event.objects:
				seen.setdefault(object_type, None)
		return list(seen)

	def variants(self, lifecycle: str | None = COMPLETE) -> dict[tuple[str, ...], list[str]]:
		"""Each distinct activity sequence and the cases that follow it, most frequent first.

		Only events with the given lifecycle count, so a start/complete pair is one step. Pass
		None to keep every event."""
		by_variant: dict[tuple[str, ...], list[str]] = defaultdict(list)
		for case_id, events in self.traces().items():
			steps = tuple(e.activity for e in events if lifecycle is None or e.lifecycle == lifecycle)
			by_variant[steps].append(case_id)
		return dict(sorted(by_variant.items(), key=lambda item: (-len(item[1]), item[0])))

	def filter(self, predicate) -> EventLog:
		return EventLog((e for e in self._events if predicate(e)), name=self.name, attributes=self.attributes)

	def filter_cases(self, case_ids: Iterable[str]) -> EventLog:
		wanted = set(case_ids)
		return self.filter(lambda e: e.case_id in wanted)

	def between(self, since: datetime | None = None, until: datetime | None = None) -> EventLog:
		return self.filter(
			lambda e: (since is None or e.timestamp >= since) and (until is None or e.timestamp < until)
		)

	def span(self) -> tuple[datetime, datetime] | None:
		if not self._events:
			return None
		return self._events[0].timestamp, self._events[-1].timestamp

	def summary(self) -> dict:
		traces = self.traces()
		span = self.span()
		return {
			"events": len(self._events),
			"cases": len(traces),
			"activities": len(self.activities()),
			"variants": len(self.variants()),
			"resources": len(self.resources()),
			"object_types": self.object_types(),
			"from": span[0].isoformat() if span else None,
			"to": span[1].isoformat() if span else None,
		}

	def to_dicts(self) -> list[dict]:
		return [event_to_dict(e) for e in self._events]

	@classmethod
	def from_dicts(cls, rows: Iterable[dict], name: str = "") -> EventLog:
		return cls((event_from_dict(row) for row in rows), name=name)


def _sort_key(event: Event):
	# Timezone-aware and naive datetimes do not compare; normalise both to UTC seconds.
	return (_to_utc(event.timestamp), event.case_id, 0 if event.lifecycle == START else 1)


def _to_utc(value: datetime) -> datetime:
	if value.tzinfo is None:
		return value.replace(tzinfo=timezone.utc)
	return value.astimezone(timezone.utc)


def seconds_between(earlier: datetime, later: datetime) -> float:
	"""Seconds from one timestamp to another, whether or not they carry a timezone. A naive
	timestamp is read as UTC, the same reading the log's ordering uses."""
	return (_to_utc(later) - _to_utc(earlier)).total_seconds()


def event_to_dict(event: Event) -> dict:
	row = {
		"case_id": event.case_id,
		"activity": event.activity,
		"timestamp": event.timestamp.isoformat(),
		"lifecycle": event.lifecycle,
	}
	if event.resource:
		row["resource"] = event.resource
	if event.attributes:
		row["attributes"] = dict(event.attributes)
	if event.objects:
		row["objects"] = {k: list(v) for k, v in event.objects.items()}
	return row


def event_from_dict(row: dict) -> Event:
	timestamp = row.get("timestamp")
	if isinstance(timestamp, str):
		timestamp = parse_timestamp(timestamp)
	return Event(
		case_id=str(row.get("case_id") or row.get("case") or ""),
		activity=str(row.get("activity") or ""),
		timestamp=timestamp,
		resource=row.get("resource") or None,
		lifecycle=row.get("lifecycle") or COMPLETE,
		attributes=dict(row.get("attributes") or {}),
		objects={k: [str(x) for x in v] for k, v in (row.get("objects") or {}).items()},
	)


def parse_timestamp(value) -> datetime:
	"""ISO 8601 (with Z accepted), Unix seconds, or a datetime."""
	if isinstance(value, datetime):
		return value
	if isinstance(value, int | float):
		return datetime.fromtimestamp(value, tz=timezone.utc)
	text = str(value).strip()
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	return datetime.fromisoformat(text)
