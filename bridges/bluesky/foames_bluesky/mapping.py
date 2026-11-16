# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Turn Bluesky documents into FoaMES machine events. Standard library only.

Bluesky (https://github.com/bluesky/bluesky, BSD-3-Clause) emits a stream of (name, document)
pairs for each run: one `start`, a `descriptor` per stream, `event` or `event_page` documents with
the readings, and one `stop`. The same stream comes back from a Tiled server
(`run.documents()`) or from a JSON Lines file written by suitcase-jsonl. `RunMapper` reads that
stream and returns the events the FoaMES webhook takes (see docs/machine-data.md in the FoaMES
repository):

- each numeric scalar reading in a selected stream becomes a `Measurement` event,
- optional per-run summaries (`mean`, `min`, `max`, `last`, `first`, `count`) become one
  `Measurement` per field at the stop document, which is what a control chart of run-to-run
  quality usually wants,
- the start and stop documents become `Message` events, so the run and its exit status show on the
  machine's timeline.

Every event carries an `id` built from Bluesky's own uids, so replaying a run (or retrying a
failed post) never stores a reading twice, and a `provenance` block (run uid, scan id, plan, stream,
sequence number, the data key's source and units, and chosen start-document metadata) that FoaMES
keeps in the Machine Event's payload.

Nothing here infers machine state: a failed or aborted run is reported as a message, never as
downtime, and an incomplete run gets no summaries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

NUMERIC_DTYPES = ("number", "integer")
SUMMARIES = ("mean", "min", "max", "first", "last", "count")
DEFAULT_MACHINE_KEYS = ("foames_machine", "beamline_id", "instrument")
DEFAULT_START_KEYS = ("sample", "proposal_id", "operator")


class MappingError(ValueError):
	pass


@dataclass
class _Run:
	uid: str
	machine: str | None
	start: dict
	streams: dict = field(default_factory=dict)  # descriptor uid -> (stream name, {key: data key})
	values: dict = field(default_factory=dict)  # measurement name -> [values in arrival order]


class RunMapper:
	"""Callable as `mapper(name, doc)`; returns a list of FoaMES event dicts (possibly empty).

	machine        the FoaMES Machine Source ID that every run's readings belong to, or None to take
	               it from the start document (first of `machine_keys` that is set)
	streams        stream names to read (default only "primary"); None reads every stream
	fields         data keys to read; None reads every numeric scalar key the descriptor declares
	prefix         prepended to each measurement name, e.g. "xrd." or "uvvis."
	readings       emit one Measurement per reading (default True)
	summaries      per-run summaries to emit at the stop document, from SUMMARIES
	messages       emit Message events for start and stop (default True)
	start_keys     start-document keys copied into each event's provenance
	"""

	def __init__(
		self,
		machine: str | None = None,
		*,
		machine_keys=DEFAULT_MACHINE_KEYS,
		streams=("primary",),
		fields=None,
		prefix: str = "",
		readings: bool = True,
		summaries=(),
		messages: bool = True,
		start_keys=DEFAULT_START_KEYS,
	):
		unknown = [s for s in summaries or () if s not in SUMMARIES]
		if unknown:
			raise MappingError(f"unknown summary {unknown[0]!r}; use {', '.join(SUMMARIES)}")
		self.machine = machine
		self.machine_keys = tuple(machine_keys or ())
		self.streams = None if streams is None else set(streams)
		self.fields = None if fields is None else set(fields)
		self.prefix = prefix or ""
		self.readings = readings
		self.summaries = tuple(summaries or ())
		self.messages = messages
		self.start_keys = tuple(start_keys or ())
		self._runs: dict[str, _Run] = {}
		self._descriptor_run: dict[str, str] = {}
		self.skipped: list[str] = []

	def __call__(self, name: str, doc: dict) -> list[dict]:
		handler = getattr(self, f"_on_{name}", None)
		if handler is None:
			# resource, datum, stream_resource, stream_datum: external (array) data, not read here.
			return []
		return handler(doc) or []

	# documents

	def _on_start(self, doc: dict) -> list[dict]:
		uid = _required(doc, "uid", "start")
		machine = self.machine or next((str(doc[k]) for k in self.machine_keys if doc.get(k)), None)
		self._runs[uid] = _Run(uid=uid, machine=machine, start=doc)
		if not machine:
			self.skipped.append(
				f"run {uid}: no machine given and none of {', '.join(self.machine_keys) or '(no keys)'} "
				"is set in its start document"
			)
			return []
		if not self.messages:
			return []
		plan = doc.get("plan_name") or "plan"
		scan = f", scan {doc['scan_id']}" if doc.get("scan_id") is not None else ""
		return [
			self._event(
				self._runs[uid],
				"Message",
				doc.get("time"),
				f"bluesky:{uid}:start",
				text=f"Bluesky run started: {plan}{scan}",
			)
		]

	def _on_descriptor(self, doc: dict) -> list[dict]:
		uid = _required(doc, "uid", "descriptor")
		run = self._runs.get(doc.get("run_start"))
		if run is None:
			return []
		stream = doc.get("name") or "primary"
		self._descriptor_run[uid] = run.uid
		if self.streams is not None and stream not in self.streams:
			return []
		keys = {}
		for key, spec in (doc.get("data_keys") or {}).items():
			if self.fields is not None and key not in self.fields:
				continue
			if _is_numeric_scalar(spec):
				keys[key] = spec
		run.streams[uid] = (stream, keys)
		return []

	def _on_event(self, doc: dict) -> list[dict]:
		run = self._run_for_descriptor(doc.get("descriptor"))
		if run is None or not run.machine:
			return []
		stream, keys = run.streams.get(doc.get("descriptor"), (None, None))
		if not keys:
			return []
		data = doc.get("data") or {}
		timestamps = doc.get("timestamps") or {}
		out = []
		for key, spec in keys.items():
			value = _finite(data.get(key))
			if value is None:
				continue
			name = self.prefix + key
			run.values.setdefault(name, []).append(value)
			if not self.readings:
				continue
			out.append(
				self._event(
					run,
					"Measurement",
					timestamps.get(key, doc.get("time")),
					f"bluesky:{doc.get('uid')}:{key}",
					name=name,
					value=value,
					units=spec.get("units"),
					extra={
						"stream": stream,
						"event_uid": doc.get("uid"),
						"seq_num": doc.get("seq_num"),
						"data_key": key,
						"source": spec.get("source"),
					},
				)
			)
		return out

	def _on_event_page(self, doc: dict) -> list[dict]:
		out = []
		for event in unpack_event_page(doc):
			out.extend(self._on_event(event))
		return out

	def _on_stop(self, doc: dict) -> list[dict]:
		run = self._runs.pop(doc.get("run_start"), None)
		for descriptor in [d for d, r in self._descriptor_run.items() if run and r == run.uid]:
			del self._descriptor_run[descriptor]
		if run is None or not run.machine:
			return []
		status = doc.get("exit_status") or "unknown"
		out = []
		if status == "success":
			for name, values in run.values.items():
				for summary in self.summaries:
					out.append(
						self._event(
							run,
							"Measurement",
							doc.get("time"),
							f"bluesky:{run.uid}:{name}:{summary}",
							name=f"{name}.{summary}",
							value=_summarise(summary, values),
							extra={"summary": summary, "readings": len(values)},
						)
					)
		if self.messages:
			reason = f": {doc['reason']}" if doc.get("reason") else ""
			out.append(
				self._event(
					run,
					"Message",
					doc.get("time"),
					f"bluesky:{run.uid}:stop",
					text=f"Bluesky run ended ({status}){reason}",
					extra={"exit_status": status, "num_events": doc.get("num_events")},
				)
			)
		return out

	# helpers

	def _run_for_descriptor(self, descriptor_uid):
		run_uid = self._descriptor_run.get(descriptor_uid)
		return self._runs.get(run_uid) if run_uid else None

	def _event(
		self,
		run,
		event_type,
		timestamp,
		event_id,
		*,
		name=None,
		value=None,
		text=None,
		units=None,
		extra=None,
	):
		provenance = {"system": "bluesky", "run_uid": run.uid}
		for key in ("scan_id", "plan_name"):
			if run.start.get(key) is not None:
				provenance[key] = run.start[key]
		for key in self.start_keys:
			if run.start.get(key) is not None:
				provenance[key] = run.start[key]
		if units:
			provenance["units"] = units
		for key, val in (extra or {}).items():
			if val is not None:
				provenance[key] = val
		event = {"machine": run.machine, "type": event_type, "id": event_id, "provenance": provenance}
		if timestamp is not None:
			event["timestamp"] = timestamp
		if name is not None:
			event["name"] = name
			event["value"] = value
		if text is not None:
			event["text"] = text
		return event


def map_documents(documents, mapper: RunMapper | None = None, **options) -> list[dict]:
	"""All events for an iterable of (name, doc) pairs."""
	mapper = mapper or RunMapper(**options)
	out = []
	for name, doc in documents:
		out.extend(mapper(name, doc))
	return out


def unpack_event_page(page: dict):
	"""Yield the event documents of an event page (the columnar form Bluesky and Tiled also use)."""
	uids = page.get("uid") or []
	data = page.get("data") or {}
	timestamps = page.get("timestamps") or {}
	times = page.get("time") or []
	seq_nums = page.get("seq_num") or []
	for i, uid in enumerate(uids):
		yield {
			"uid": uid,
			"descriptor": page.get("descriptor"),
			"time": times[i] if i < len(times) else None,
			"seq_num": seq_nums[i] if i < len(seq_nums) else None,
			"data": {k: v[i] for k, v in data.items() if i < len(v)},
			"timestamps": {k: v[i] for k, v in timestamps.items() if i < len(v)},
		}


def _is_numeric_scalar(spec: dict) -> bool:
	if not isinstance(spec, dict) or spec.get("external"):
		return False
	if spec.get("dtype") not in NUMERIC_DTYPES:
		return False
	return not spec.get("shape")


def _finite(value) -> float | None:
	if isinstance(value, bool) or value is None:
		return None
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if math.isfinite(number) else None


def _summarise(summary: str, values: list[float]) -> float:
	if summary == "mean":
		return sum(values) / len(values)
	if summary == "min":
		return min(values)
	if summary == "max":
		return max(values)
	if summary == "first":
		return values[0]
	if summary == "last":
		return values[-1]
	return float(len(values))


def _required(doc: dict, key: str, name: str):
	if not isinstance(doc, dict) or not doc.get(key):
		raise MappingError(f"{name} document has no {key}")
	return doc[key]
