# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Shift calendars as pure arithmetic: which production windows a shift pattern holds on a day.

A pattern is a set of shifts, each with a start time, a length in minutes and the weekdays it runs
on, plus non-working dates. A shift belongs to the day it starts on: a night shift from 22:00 for
480 minutes that starts on Monday is Monday's shift and ends on Tuesday at 06:00, and a holiday on
Monday cancels it. No Frappe dependency.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class Shift:
	name: str
	start: time
	minutes: float
	weekdays: frozenset[int]  # 0 = Monday, as date.weekday()


@dataclass(frozen=True)
class Window:
	shift: str | None
	start: datetime
	end: datetime
	minutes: float


def parse_time(value) -> time:
	"""A time from a `time`, a `timedelta` (how MariaDB returns a Time column) or "HH:MM[:SS]"."""
	if isinstance(value, time):
		return value
	if isinstance(value, timedelta):
		seconds = int(value.total_seconds()) % 86400
		return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)
	parts = [int(float(p)) for p in str(value).strip().split(":")]
	while len(parts) < 3:
		parts.append(0)
	return time(parts[0], parts[1], parts[2])


def make_shift(name: str, start, minutes, **days) -> Shift:
	"""A Shift from row-like values: `days` holds monday=1, tuesday=0, ... flags."""
	weekdays = frozenset(i for i, day in enumerate(WEEKDAYS) if days.get(day))
	return Shift(name=name, start=parse_time(start), minutes=float(minutes or 0), weekdays=weekdays)


def windows_for_day(day: date, shifts: list[Shift], holidays=frozenset()) -> list[Window]:
	"""The windows of the shifts that start on `day`, in start order. None on a holiday."""
	if day in holidays:
		return []
	out = []
	for s in shifts:
		if day.weekday() not in s.weekdays or s.minutes <= 0:
			continue
		start = datetime.combine(day, s.start)
		out.append(Window(s.name, start, start + timedelta(minutes=s.minutes), s.minutes))
	return sorted(out, key=lambda w: w.start)


def windows_between(
	start: datetime, end: datetime, shifts: list[Shift], holidays=frozenset()
) -> list[Window]:
	"""Every window that overlaps [start, end), clipped to it. A shift that started the day before
	`start` and runs into it is included with its clipped part."""
	out = []
	day = start.date() - timedelta(days=1)
	while datetime.combine(day, time()) < end:
		for w in windows_for_day(day, shifts, holidays):
			a, b = max(w.start, start), min(w.end, end)
			if b > a:
				out.append(Window(w.shift, a, b, (b - a).total_seconds() / 60.0))
		day += timedelta(days=1)
	return out


def window_at(moment: datetime, shifts: list[Shift], holidays=frozenset()) -> Window | None:
	"""The window that contains `moment`, if any (its own day's shifts or a night shift from the
	day before)."""
	for day in (moment.date() - timedelta(days=1), moment.date()):
		for w in windows_for_day(day, shifts, holidays):
			if w.start <= moment < w.end:
				return w
	return None


def problems(shifts: list[Shift]) -> list[str]:
	"""What is wrong with a pattern: bad lengths, duplicate names, shifts that overlap.

	Overlap is checked over two consecutive weeks, so a Sunday night shift that runs into Monday
	morning is caught too.
	"""
	found = []
	names = [s.name for s in shifts]
	for name in sorted({n for n in names if names.count(n) > 1}):
		found.append(f"Shift {name} is listed more than once")
	for s in shifts:
		if s.minutes <= 0 or s.minutes > MINUTES_PER_DAY:
			found.append(f"Shift {s.name} must last more than 0 and at most {MINUTES_PER_DAY} minutes")
		if not s.weekdays:
			found.append(f"Shift {s.name} runs on no weekday")
	if found:
		return found
	monday = date(2024, 1, 1)  # a Monday
	windows = [w for i in range(14) for w in windows_for_day(monday + timedelta(days=i), shifts)]
	windows.sort(key=lambda w: w.start)
	seen = set()
	for i, a in enumerate(windows):
		for b in windows[i + 1 :]:
			if b.start >= a.end:
				break
			pair = tuple(sorted((a.shift, b.shift)))
			if pair not in seen:
				seen.add(pair)
				found.append(f"Shifts {pair[0]} and {pair[1]} overlap")
	return found
