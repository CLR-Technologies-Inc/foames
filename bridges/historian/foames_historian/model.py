# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""What every historian source returns, and the time and aggregate helpers they share.

Standard library only. A source turns its own rows or JSON into `Sample`s with an aware UTC
timestamp, a value (a finite float, a string, or None for "no value") and a quality of `good`,
`uncertain` or `bad`. Everything after that (the tag map, the events, the checkpoint) works on
samples and does not care which historian they came from.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

GOOD, UNCERTAIN, BAD = "good", "uncertain", "bad"
QUALITIES = (GOOD, UNCERTAIN, BAD)

# Aggregates every source understands. Each source maps them to its own names; a source that
# cannot aggregate on the server reads raw samples and calls `aggregate()` below.
AGGREGATES = ("mean", "min", "max", "first", "last", "count", "sum")

UTC = timezone.utc
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)\s*$")
_FRACTION = re.compile(r"(\.\d+)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}


class HistorianError(RuntimeError):
	"""The historian could not be reached, refused the query, or answered with something unreadable."""


@dataclass(frozen=True)
class Sample:
	tag: str
	timestamp: datetime
	value: float | str | None
	quality: str = GOOD
	units: str | None = None
	extra: dict = field(default_factory=dict, compare=False, hash=False)


# time


def parse_time(value, *, now: datetime | None = None) -> datetime:
	"""An aware UTC datetime from ISO 8601, Unix seconds, `now`, or `now-<duration>` (`now-2h`).

	A naive ISO string is taken as UTC: historians store UTC and so does this bridge."""
	if isinstance(value, datetime):
		return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		return from_epoch_seconds(value)
	if not isinstance(value, str) or not value.strip():
		raise ValueError(f"not a time: {value!r}")
	text = value.strip()
	now = now or datetime.now(UTC)
	if text == "now":
		return now
	if text.startswith("now-"):
		return now - parse_duration(text[4:])
	try:
		return from_epoch_seconds(float(text))
	except ValueError:
		pass
	if text.endswith(("Z", "z")):
		text = text[:-1] + "+00:00"
	# PI and .NET write seven fractional digits, others one to nine; Python 3.10 reads three or six.
	text = _FRACTION.sub(lambda m: "." + m.group(1)[1:7].ljust(6, "0"), text, count=1)
	try:
		parsed = datetime.fromisoformat(text)
	except ValueError as e:
		raise ValueError(f"not a time: {value!r}") from e
	return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_duration(value) -> timedelta:
	"""`500ms`, `30s`, `5m`, `1h`, `1d`, or a number of seconds."""
	if isinstance(value, timedelta):
		return value
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		seconds = float(value)
	else:
		match = _DURATION.match(str(value or ""))
		if not match:
			raise ValueError(f"not a duration: {value!r} (use 500ms, 30s, 5m, 1h or 1d)")
		seconds = float(match.group(1)) * _UNIT_SECONDS[match.group(2)]
	if seconds <= 0:
		raise ValueError(f"a duration must be positive: {value!r}")
	return timedelta(seconds=seconds)


def from_epoch_seconds(seconds: float) -> datetime:
	return _EPOCH + timedelta(seconds=float(seconds))


def from_epoch_ms(ms: float) -> datetime:
	return _EPOCH + timedelta(milliseconds=float(ms))


def epoch_ms(moment: datetime) -> int:
	"""Whole milliseconds since the epoch (exact, no float rounding)."""
	delta = moment.astimezone(UTC) - _EPOCH
	return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


def iso(moment: datetime) -> str:
	"""ISO 8601 in UTC with a Z and millisecond precision, the form the FoaMES webhook takes."""
	moment = moment.astimezone(UTC)
	return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def floor_time(moment: datetime, interval: timedelta) -> datetime:
	"""The start of the bucket of length `interval` (aligned to the Unix epoch) holding `moment`."""
	step = epoch_ms(_EPOCH + interval)
	return from_epoch_ms(epoch_ms(moment) // step * step)


# values


def finite_or_none(value):
	"""A finite float, a string, or None. Booleans become 1.0 / 0.0 (historians store them as ints)."""
	if value is None:
		return None
	if isinstance(value, bool):
		return 1.0 if value else 0.0
	if isinstance(value, (int, float)):
		number = float(value)
		return number if math.isfinite(number) else None
	if isinstance(value, str):
		return value
	try:
		number = float(value)  # Decimal and other numeric types from DB drivers
	except (TypeError, ValueError):
		return str(value)
	return number if math.isfinite(number) else None


def opc_quality(code) -> str:
	"""Quality from an OPC-style integer code, as Ignition's `dataintegrity` and many SQL historians
	store it: 192-255 good, 64-127 uncertain, anything else bad. None (no quality column) is good."""
	if code is None:
		return GOOD
	try:
		code = int(code)
	except (TypeError, ValueError):
		return BAD
	if 192 <= code <= 255:
		return GOOD
	if 64 <= code <= 127:
		return UNCERTAIN
	return BAD


# client-side aggregation


def aggregate(samples, start: datetime, end: datetime, interval: timedelta, how: str) -> list[Sample]:
	"""Bucket raw samples into [start, end) by `interval` (epoch-aligned) and reduce each bucket.

	Only good, numeric samples count; `uncertain` ones are kept but mark their bucket uncertain.
	A bucket with no usable sample is left out (no value is invented for it). The sample time is
	the bucket's start, as the server-side aggregates of PI, InfluxDB and TimescaleDB report it.
	`mean` here is the arithmetic mean of the samples, not time-weighted."""
	if how not in AGGREGATES:
		raise ValueError(f"unknown aggregate {how!r}; use {', '.join(AGGREGATES)}")
	buckets: dict[datetime, list[Sample]] = {}
	for sample in samples:
		if sample.quality == BAD or not isinstance(sample.value, float):
			continue
		if not (start <= sample.timestamp < end):
			continue
		buckets.setdefault(floor_time(sample.timestamp, interval), []).append(sample)
	out = []
	for bucket_start in sorted(buckets):
		members = sorted(buckets[bucket_start], key=lambda s: s.timestamp)
		values = [s.value for s in members]
		quality = UNCERTAIN if any(s.quality == UNCERTAIN for s in members) else GOOD
		out.append(
			Sample(
				tag=members[0].tag,
				timestamp=bucket_start,
				value=_reduce(how, values),
				quality=quality,
				units=members[0].units,
				extra={"aggregate": how, "samples": len(values)},
			)
		)
	return out


def _reduce(how: str, values: list[float]) -> float:
	if how == "mean":
		return sum(values) / len(values)
	if how == "min":
		return min(values)
	if how == "max":
		return max(values)
	if how == "first":
		return values[0]
	if how == "last":
		return values[-1]
	if how == "sum":
		return sum(values)
	return float(len(values))
