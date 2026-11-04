# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Shift calendars, without a site."""

import unittest
from datetime import date, datetime, time, timedelta

from foames.foames_mes.shifts import (
	Shift,
	make_shift,
	parse_time,
	problems,
	window_at,
	windows_between,
	windows_for_day,
)

WEEKDAYS = dict(monday=1, tuesday=1, wednesday=1, thursday=1, friday=1)
MONDAY = date(2026, 11, 2)


def three_shifts():
	return [
		make_shift("Early", "06:00", 480, **WEEKDAYS),
		make_shift("Late", "14:00:00", 480, **WEEKDAYS),
		make_shift("Night", time(22, 0), 480, **WEEKDAYS),
	]


class TestParseTime(unittest.TestCase):
	def test_forms(self):
		self.assertEqual(parse_time("6:30"), time(6, 30))
		self.assertEqual(parse_time("22:00:15"), time(22, 0, 15))
		self.assertEqual(parse_time(timedelta(hours=14, minutes=5)), time(14, 5))
		self.assertEqual(parse_time(time(1, 2, 3)), time(1, 2, 3))
		self.assertEqual(parse_time("06:00:00.000000"), time(6, 0))


class TestWindows(unittest.TestCase):
	def test_three_shift_weekday(self):
		windows = windows_for_day(MONDAY, three_shifts())
		self.assertEqual([w.shift for w in windows], ["Early", "Late", "Night"])
		night = windows[2]
		self.assertEqual(night.start, datetime(2026, 11, 2, 22, 0))
		self.assertEqual(night.end, datetime(2026, 11, 3, 6, 0))
		self.assertEqual(sum(w.minutes for w in windows), 1440)

	def test_weekend_and_holiday(self):
		self.assertEqual(windows_for_day(date(2026, 11, 7), three_shifts()), [])
		self.assertEqual(windows_for_day(MONDAY, three_shifts(), {MONDAY}), [])
		self.assertEqual(len(windows_for_day(MONDAY + timedelta(days=1), three_shifts(), {MONDAY})), 3)

	def test_zero_length_shift_is_ignored(self):
		self.assertEqual(windows_for_day(MONDAY, [make_shift("X", "06:00", 0, monday=1)]), [])

	def test_between_includes_the_night_shift_from_the_day_before(self):
		start, end = datetime(2026, 11, 3, 0, 0), datetime(2026, 11, 3, 12, 0)
		windows = windows_between(start, end, three_shifts())
		self.assertEqual([(w.shift, w.minutes) for w in windows], [("Night", 360), ("Early", 360)])
		self.assertEqual(windows[0].start, start)

	def test_window_at(self):
		shifts = three_shifts()
		self.assertEqual(window_at(datetime(2026, 11, 3, 3, 0), shifts).shift, "Night")
		self.assertEqual(window_at(datetime(2026, 11, 3, 6, 0), shifts).shift, "Early")
		self.assertEqual(window_at(datetime(2026, 11, 3, 13, 59), shifts).shift, "Early")
		# Friday's night shift runs into Saturday; nothing starts on Saturday.
		self.assertEqual(window_at(datetime(2026, 11, 7, 5, 0), shifts).shift, "Night")
		self.assertIsNone(window_at(datetime(2026, 11, 7, 7, 0), shifts))


class TestProblems(unittest.TestCase):
	def test_valid_pattern(self):
		self.assertEqual(problems(three_shifts()), [])
		self.assertEqual(
			problems([make_shift("All", "00:00", 1440, **dict.fromkeys(WEEKDAYS, 1), saturday=1, sunday=1)]),
			[],
		)

	def test_overlap_and_bad_rows(self):
		self.assertEqual(
			problems([make_shift("A", "06:00", 600, monday=1), make_shift("B", "14:00", 480, monday=1)]),
			["Shifts A and B overlap"],
		)
		self.assertIn(
			"Shift A is listed more than once", problems([make_shift("A", "06:00", 60, monday=1)] * 2)
		)
		self.assertTrue(problems([make_shift("A", "06:00", 1500, monday=1)]))
		self.assertTrue(problems([Shift("A", time(6), 60, frozenset())]))

	def test_sunday_night_into_monday_morning(self):
		found = problems(
			[make_shift("Sun Night", "22:00", 600, sunday=1), make_shift("Mon Early", "06:00", 480, monday=1)]
		)
		self.assertEqual(found, ["Shifts Mon Early and Sun Night overlap"])


if __name__ == "__main__":
	unittest.main()
