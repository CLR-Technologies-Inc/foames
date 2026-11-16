# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The read-only contract every historian source keeps."""

from __future__ import annotations

from datetime import datetime, timedelta

from foames_historian.model import AGGREGATES, Sample, aggregate


class Source:
	"""A historian, read-only.

	read(tag, start, end)                         raw samples with start <= t < end, oldest first
	read(tag, start, end, interval=, aggregate=)  one sample per whole bucket, stamped at its start

	Subclasses implement `_read_raw` and, when the historian aggregates on the server,
	`_read_aggregated`; otherwise raw samples are bucketed here (see `model.aggregate`).
	`name` identifies the source in event ids and provenance, so keep it stable once events have
	been sent."""

	kind = "source"

	def __init__(self, name: str):
		self.name = name or self.kind

	def read(
		self,
		tag: str,
		start: datetime,
		end: datetime,
		*,
		interval: timedelta | None = None,
		aggregate: str | None = None,
	) -> list[Sample]:
		if end <= start:
			return []
		if interval is None:
			samples = self._read_raw(tag, start, end)
			return sorted((s for s in samples if start <= s.timestamp < end), key=lambda s: s.timestamp)
		how = aggregate or "mean"
		if how not in AGGREGATES:
			raise ValueError(f"unknown aggregate {how!r}; use {', '.join(AGGREGATES)}")
		samples = self._read_aggregated(tag, start, end, interval, how)
		return sorted((s for s in samples if start <= s.timestamp < end), key=lambda s: s.timestamp)

	def _read_raw(self, tag, start, end) -> list[Sample]:
		raise NotImplementedError

	def _read_aggregated(self, tag, start, end, interval, how) -> list[Sample]:
		return aggregate(self._read_raw(tag, start, end), start, end, interval, how)

	def close(self):
		pass

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.close()
