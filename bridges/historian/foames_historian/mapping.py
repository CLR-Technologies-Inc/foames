# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Turn historian samples into FoaMES machine events. Standard library only.

A tag map says, for each historian tag, which FoaMES Machine it belongs to and what it becomes
(see docs/machine-data.md in the FoaMES repository for the event shapes):

	{"tag": "\\\\PI01\\P1.Temp", "machine": "press-1", "type": "Measurement", "name": "temperature"}
	{"tag": "[default]L1/P1/Good", "machine": "press-1", "type": "Count", "counter": "good"}
	{"tag": "[default]L1/P1/State", "machine": "press-1", "type": "State", "states": {"0": "Down", "1": "Running"}}
	{"tag": "plant/temp?line=L1", "machine": "oven-2", "name": "temp.mean_1m", "interval": "1m", "aggregate": "mean"}

Rules, which follow the FoaMES invariants:

- A Count carries the historian's running total and FoaMES computes the delta, so a counter is
  never aggregated here and nothing is added up on this side.
- A State comes only from a recorded value. A numeric state needs a `states` map; a value that is
  not in the map is skipped and reported, never guessed.
- Bad-quality samples (and PI system digital states) are never sent; uncertain ones are sent and
  marked in the provenance, unless the entry sets `"uncertain": false`.
- Every event has an `id` built from the source name, the tag map entry and the sample time, so a
  replayed window or a retried post never stores a value twice.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import timedelta

from foames_historian.model import AGGREGATES, BAD, UNCERTAIN, Sample, epoch_ms, iso, parse_duration

EVENT_TYPES = ("Measurement", "Count", "State", "Message")
_SOURCE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class MappingError(ValueError):
	pass


@dataclass
class TagMapping:
	tag: str
	machine: str
	type: str = "Measurement"
	name: str | None = None
	counter: str | None = None
	states: dict = field(default_factory=dict)
	interval: timedelta | None = None
	aggregate: str | None = None
	scale: float = 1.0
	offset: float = 0.0
	uncertain: bool = True

	@classmethod
	def from_dict(cls, raw: dict) -> TagMapping:
		if not isinstance(raw, dict):
			raise MappingError(f"a tag map entry must be an object, not {raw!r}")
		unknown = set(raw) - {f for f in cls.__dataclass_fields__}
		if unknown:
			raise MappingError(f"tag map entry {raw.get('tag')!r}: unknown keys {', '.join(sorted(unknown))}")
		entry = dict(raw)
		if entry.get("interval") is not None:
			entry["interval"] = parse_duration(entry["interval"])
		mapping = cls(tag=entry.pop("tag", None), machine=entry.pop("machine", None), **entry)
		mapping.validate()
		return mapping

	def validate(self):
		where = f"tag map entry {self.tag!r}"
		if not self.tag or not isinstance(self.tag, str):
			raise MappingError("every tag map entry needs a tag")
		if not self.machine:
			raise MappingError(f"{where} needs a machine (the FoaMES Machine's Source ID)")
		if self.type not in EVENT_TYPES:
			raise MappingError(f"{where}: type must be one of {', '.join(EVENT_TYPES)}")
		if self.type == "Count" and not self.counter:
			raise MappingError(f"{where}: a Count needs a counter name, such as good or scrap")
		if self.aggregate is not None and self.interval is None:
			raise MappingError(f"{where}: an aggregate needs an interval")
		if self.interval is not None:
			if self.type != "Measurement":
				raise MappingError(
					f"{where}: only a Measurement can be aggregated; send a {self.type} as recorded"
				)
			self.aggregate = self.aggregate or "mean"
			if self.aggregate not in AGGREGATES:
				raise MappingError(f"{where}: aggregate must be one of {', '.join(AGGREGATES)}")
		if self.type == "State" and not isinstance(self.states, dict):
			raise MappingError(f"{where}: states must be an object of value -> state")
		self.states = {_state_key(k): v for k, v in (self.states or {}).items()}

	@property
	def measurement_name(self) -> str:
		if self.name:
			return self.name
		base = re.split(r"[/\\|.\]]", self.tag.split("?")[0])[-1] or self.tag
		return f"{base}.{self.aggregate}" if self.aggregate else base

	@property
	def key(self) -> str:
		"""A short, stable id for this entry: what it reads and what it becomes."""
		parts = [self.tag, self.machine, self.type, self.name or "", self.counter or "", self.aggregate or ""]
		if self.interval is not None:
			parts.append(str(int(self.interval.total_seconds() * 1000)))
		return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]


def load_tag_map(entries) -> list[TagMapping]:
	mappings = [TagMapping.from_dict(e) for e in entries or []]
	if not mappings:
		raise MappingError("the tag map is empty")
	seen = {}
	for m in mappings:
		if m.key in seen:
			raise MappingError(f"tag map entry {m.tag!r} is listed twice")
		seen[m.key] = m
	return mappings


def check_source_name(name: str) -> str:
	if not isinstance(name, str) or not _SOURCE_NAME.match(name):
		raise MappingError(
			f"source name {name!r} must be 1-40 letters, digits, '.', '_' or '-' (it is part of every event id)"
		)
	return name


class SampleMapper:
	"""events(mapping, samples) -> list of FoaMES event dicts; `skipped` collects the reasons."""

	def __init__(self, source_name: str, source_kind: str = "historian"):
		self.source_name = check_source_name(source_name)
		self.source_kind = source_kind
		self.skipped: list[str] = []

	def events(self, mapping: TagMapping, samples) -> list[dict]:
		out = []
		for sample in samples:
			event = self.event(mapping, sample)
			if event is not None:
				out.append(event)
		return out

	def event(self, mapping: TagMapping, sample: Sample) -> dict | None:
		if sample.quality == BAD:
			self._skip(mapping, sample, "bad quality")
			return None
		if sample.quality == UNCERTAIN and not mapping.uncertain:
			self._skip(mapping, sample, "uncertain quality")
			return None
		value = sample.value
		body: dict = {}
		if mapping.type in ("Measurement", "Count"):
			if not isinstance(value, float):
				self._skip(mapping, sample, f"not a number ({value!r})")
				return None
			value = value * mapping.scale + mapping.offset
			if mapping.type == "Measurement":
				body = {"name": mapping.measurement_name, "value": value}
			else:
				body = {"counter": mapping.counter, "value": value}
		elif mapping.type == "State":
			state = mapping.states.get(_state_key(value)) if mapping.states else None
			if state is None and isinstance(value, str) and not mapping.states:
				state = value
			if not state:
				self._skip(mapping, sample, f"state value {value!r} is not in the states map")
				return None
			body = {"state": state}
		else:
			if value is None:
				self._skip(mapping, sample, "empty message")
				return None
			body = {"text": str(value) if not isinstance(value, float) else _number_text(value)}

		suffix = f":{mapping.aggregate}" if mapping.aggregate else ""
		micros = epoch_ms(sample.timestamp) * 1000 + sample.timestamp.microsecond % 1000
		provenance = {
			"system": "historian",
			"historian": self.source_kind,
			"source": self.source_name,
			"tag": mapping.tag,
			"quality": sample.quality,
		}
		if sample.units:
			provenance["units"] = sample.units
		if mapping.interval is not None:
			provenance["interval_s"] = mapping.interval.total_seconds()
		if mapping.scale != 1.0 or mapping.offset != 0.0:
			provenance["raw_value"] = sample.value
		for key, val in (sample.extra or {}).items():
			if val is not None:
				provenance[key] = val
		return {
			"machine": mapping.machine,
			"type": mapping.type,
			"timestamp": iso(sample.timestamp),
			"id": f"hist:{self.source_name}:{mapping.key}:{micros}{suffix}",
			"provenance": provenance,
			**body,
		}

	def _skip(self, mapping, sample, reason):
		self.skipped.append(f"{mapping.tag} at {iso(sample.timestamp)}: {reason}")


def _state_key(value) -> str:
	"""Map keys and values compare as text, with 1, 1.0 and "1" all the same key."""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	if isinstance(value, bool):
		return "1" if value else "0"
	text = str(value).strip()
	try:
		number = float(text)
	except ValueError:
		return text
	return str(int(number)) if number.is_integer() else text


def _number_text(value: float) -> str:
	return str(int(value)) if value.is_integer() else repr(value)
