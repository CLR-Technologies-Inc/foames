# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Incremental sync: read each mapped tag since the last window, post the events, move on.

Each tag map entry has its own checkpoint, the end of the last window that was posted without an
error. The next window starts there and ends `lag` before now, so values the historian is still
receiving through store-and-forward are read on a later pass rather than missed. An aggregated
entry only ever reads whole buckets. A window is at most `max_window` long, so catching up after a
long outage happens in steps, each one checkpointed.

The checkpoint advances only after FoaMES answered. Events FoaMES rejected for another reason
than "already stored" are reported (and make the run exit non-zero) but do not hold the
checkpoint back, or one unmapped machine would stop every other tag; replay a window with
`--start` after fixing the cause, and the ids keep that from storing anything twice.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from foames_historian.mapping import SampleMapper, TagMapping
from foames_historian.model import UTC, HistorianError, epoch_ms, floor_time, from_epoch_ms, iso

DUPLICATE = "duplicate event id"


class Checkpoint:
	"""{tag map entry key: window end in epoch ms}, kept in a JSON file and written atomically."""

	def __init__(self, path: str | None = None):
		self.path = path
		self.data: dict[str, dict] = {}
		if path and os.path.exists(path):
			try:
				# The operator names the checkpoint file on the command line; this is not request input.
				with open(path, encoding="utf-8") as f:  # nosemgrep
					self.data = json.load(f).get("tags", {})
			except (OSError, ValueError) as e:
				raise HistorianError(f"cannot read the checkpoint {path}: {e}") from e

	def get(self, mapping: TagMapping) -> datetime | None:
		entry = self.data.get(mapping.key)
		return from_epoch_ms(entry["until_ms"]) if entry else None

	def set(self, mapping: TagMapping, until: datetime):
		self.data[mapping.key] = {
			"tag": mapping.tag,
			"machine": mapping.machine,
			"until": iso(until),
			"until_ms": epoch_ms(until),
		}

	def save(self):
		if not self.path:
			return
		directory = os.path.dirname(os.path.abspath(self.path))
		fd, tmp = tempfile.mkstemp(prefix=".checkpoint-", dir=directory)
		try:
			with os.fdopen(fd, "w", encoding="utf-8") as f:
				json.dump({"tags": self.data}, f, indent=1, sort_keys=True)
			os.replace(tmp, self.path)
		except BaseException:
			if os.path.exists(tmp):
				os.unlink(tmp)
			raise


@dataclass
class SyncResult:
	read: int = 0
	events: int = 0
	accepted: int = 0
	duplicates: int = 0
	rejected: list = field(default_factory=list)
	skipped: list = field(default_factory=list)
	errors: list = field(default_factory=list)
	windows: dict = field(default_factory=dict)  # tag -> (start, end) read
	caught_up: bool = True

	@property
	def ok(self) -> bool:
		return not self.rejected and not self.errors


def window_for(
	mapping: TagMapping,
	since: datetime | None,
	*,
	now: datetime,
	lag: timedelta,
	initial: timedelta,
	max_window: timedelta,
):
	"""(start, end, caught_up) for the next read of one entry, or None when there is nothing new."""
	end = now - lag
	start = since or (end - initial)
	if mapping.interval is not None:
		start = floor_time(start, mapping.interval)
		end = floor_time(end, mapping.interval)
	caught_up = True
	if end - start > max_window:
		end = start + max_window
		if mapping.interval is not None:
			end = floor_time(end, mapping.interval)
			if end <= start:
				end = start + mapping.interval
		caught_up = False
	if end <= start:
		return None
	return start, end, caught_up


def sync_once(
	source,
	mappings: list[TagMapping],
	send,
	checkpoint: Checkpoint,
	*,
	now: datetime | None = None,
	start: datetime | None = None,
	end: datetime | None = None,
	lag: timedelta = timedelta(minutes=2),
	initial: timedelta = timedelta(hours=1),
	max_window: timedelta = timedelta(days=1),
	dry_run: bool = False,
) -> tuple[SyncResult, list[dict]]:
	"""One pass over every entry. `send(events)` posts and returns {"accepted", "rejected"}.

	`start` / `end` replay a fixed window (the checkpoint is then neither read nor written)."""
	now = (now or datetime.now(UTC)).astimezone(UTC)
	replay = start is not None
	result = SyncResult()
	mapper = SampleMapper(source.name, source.kind)
	events: list[dict] = []
	advanced: list[tuple[TagMapping, datetime]] = []

	for mapping in mappings:
		if replay:
			stop = end or now
			if mapping.interval is not None:
				w_start, w_end = floor_time(start, mapping.interval), floor_time(stop, mapping.interval)
			else:
				w_start, w_end = start, stop
			if w_end <= w_start:
				continue
		else:
			window = window_for(
				mapping, checkpoint.get(mapping), now=now, lag=lag, initial=initial, max_window=max_window
			)
			if window is None:
				continue
			w_start, w_end, caught_up = window
			result.caught_up &= caught_up
		try:
			samples = source.read(
				mapping.tag, w_start, w_end, interval=mapping.interval, aggregate=mapping.aggregate
			)
		except HistorianError as e:
			result.errors.append(f"{mapping.tag}: {e}")
			continue
		result.read += len(samples)
		result.windows[mapping.tag] = (iso(w_start), iso(w_end))
		events.extend(mapper.events(mapping, samples))
		advanced.append((mapping, w_end))

	# Oldest first across all tags, so FoaMES sees each counter's readings in order.
	events.sort(key=lambda e: (e["timestamp"], e["id"]))
	result.events = len(events)
	result.skipped = mapper.skipped
	if dry_run:
		return result, events

	if events:
		answer = send(events)
		result.accepted = len(answer.get("accepted") or [])
		for rejected in answer.get("rejected") or []:
			if rejected.get("reason") == DUPLICATE:
				result.duplicates += 1
			else:
				result.rejected.append(rejected)
	if not replay:
		for mapping, w_end in advanced:
			checkpoint.set(mapping, w_end)
		checkpoint.save()
	return result, events
