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

"""Operator recognition rules, without a site."""

import unittest
from datetime import date, datetime

from foames.foames_mes.recognition import (
	DEFAULT_THRESHOLDS,
	check_recognition,
	due_milestones,
	floor_items,
	last_complete_week,
	milestone_key,
	parse_thresholds,
	summarize_periods,
	team_highlights,
	week_start,
)


class TestCheckRecognition(unittest.TestCase):
	def test_kudos_to_a_person(self):
		self.assertEqual(check_recognition("Kudos", "Person", "ana@x", None, "Great save", "bo@x"), [])

	def test_nobody_recognizes_themselves(self):
		problems = check_recognition("Kudos", "Person", "ana@x", None, "Me again", "ana@x")
		self.assertEqual(len(problems), 1)
		self.assertIn("yourself", problems[0])

	def test_team_needs_a_name(self):
		self.assertTrue(check_recognition("Kudos", "Team", None, "  ", "Well done", "bo@x"))
		self.assertEqual(check_recognition("Kudos", "Team", None, "Line 2", "Well done", "bo@x"), [])

	def test_message_is_required(self):
		self.assertEqual(check_recognition("Kudos", "Person", "ana@x", None, " Thanks ", "bo@x"), [])
		self.assertTrue(check_recognition("Kudos", "Person", "ana@x", None, " ok ", "bo@x"))
		self.assertTrue(check_recognition("Kudos", "Person", "ana@x", None, "  ", "bo@x"))

	def test_people_cannot_give_system_kinds(self):
		self.assertTrue(check_recognition("Milestone", "Person", "ana@x", None, "100 calls", "bo@x"))
		self.assertEqual(
			check_recognition("Milestone", "Person", "ana@x", None, "100 calls", None, system=True), []
		)

	def test_unknown_values(self):
		self.assertTrue(check_recognition("Ranking", "Person", "ana@x", None, "Top", "bo@x"))
		self.assertTrue(check_recognition("Kudos", "Robot", "ana@x", None, "Hi there", "bo@x"))


class TestThresholds(unittest.TestCase):
	def test_parse(self):
		self.assertEqual(parse_thresholds("50, 10 ,1;10,x,-3,0"), (1, 10, 50))
		self.assertEqual(parse_thresholds(""), DEFAULT_THRESHOLDS)
		self.assertEqual(parse_thresholds("none"), DEFAULT_THRESHOLDS)


class TestMilestones(unittest.TestCase):
	def test_first_one(self):
		out = due_milestones({"ana@x": {"andon_answered": 1}}, set(), (1, 10))
		self.assertEqual(len(out), 1)
		self.assertEqual(out[0]["key"], milestone_key("ana@x", "andon_answered", 1))
		self.assertEqual(out[0]["message"], "First andon call answered")

	def test_only_the_highest_new_threshold(self):
		out = due_milestones({"ana@x": {"suggestions_done": 30}}, set(), (1, 10, 25, 50))
		self.assertEqual([m["threshold"] for m in out], [25])
		self.assertEqual(out[0]["message"], "25 suggestions carried out")

	def test_nothing_again_once_given(self):
		given = {milestone_key("ana@x", "andon_answered", 10)}
		self.assertEqual(due_milestones({"ana@x": {"andon_answered": 12}}, given, (1, 10, 25)), [])

	def test_lower_threshold_added_later_is_not_given_after_a_higher_one(self):
		given = {milestone_key("ana@x", "andon_answered", 25)}
		self.assertEqual(due_milestones({"ana@x": {"andon_answered": 30}}, given, (1, 5, 10, 25)), [])

	def test_next_threshold(self):
		given = {milestone_key("ana@x", "andon_answered", t) for t in (1, 10)}
		out = due_milestones({"ana@x": {"andon_answered": 26}}, given, (1, 10, 25, 50))
		self.assertEqual([m["threshold"] for m in out], [25])

	def test_opted_out_and_unknown_metrics(self):
		counts = {"ana@x": {"andon_answered": 10}, "bo@x": {"andon_answered": 10, "scrap_made": 99}}
		out = due_milestones(counts, set(), (1, 10), skip_users={"ana@x"})
		self.assertEqual([(m["recipient"], m["metric"]) for m in out], [("bo@x", "andon_answered")])

	def test_not_reached(self):
		self.assertEqual(due_milestones({"ana@x": {"ideas_credited": 0}}, set(), (1,)), [])


class TestWeeks(unittest.TestCase):
	def test_week_start_is_monday(self):
		self.assertEqual(week_start(date(2026, 11, 14)), date(2026, 11, 9))  # a Saturday
		self.assertEqual(week_start(datetime(2026, 11, 9, 23, 0)), date(2026, 11, 9))

	def test_last_complete_week(self):
		self.assertEqual(last_complete_week(date(2026, 11, 16)), (date(2026, 11, 9), date(2026, 11, 16)))
		self.assertEqual(last_complete_week(date(2026, 11, 15)), (date(2026, 11, 2), date(2026, 11, 9)))


def week(oee, planned=2400, good=1000, scrap=10):
	return {"planned_minutes": planned, "oee": oee, "good": good, "scrap": scrap, "quality": None}


class TestTeamHighlights(unittest.TestCase):
	monday = date(2026, 11, 9)

	def codes(self, this_week, history, andon=None, **kw):
		return [h["code"] for h in team_highlights("Line 1", self.monday, this_week, history, andon, **kw)]

	def test_summarize_weights_oee_by_planned_minutes(self):
		s = summarize_periods(
			[
				{"planned_minutes": 480, "oee": 50, "good_count": 90, "scrap_count": 10},
				{"planned_minutes": 1440, "oee": 70, "good_count": 100, "scrap_count": 0},
				{"planned_minutes": 0, "oee": 0, "good_count": 0, "scrap_count": 0},
			]
		)
		self.assertAlmostEqual(s["oee"], 65.0)
		self.assertEqual((s["good"], s["scrap"]), (190, 10))
		self.assertAlmostEqual(s["quality"], 95.0)
		self.assertIsNone(summarize_periods([])["oee"])

	def test_oee_up(self):
		out = team_highlights("Line 1", self.monday, week(72), [week(65)])
		self.assertEqual([h["code"] for h in out], ["oee-up"])
		self.assertEqual(out[0]["key"], "team:Line 1:2026-11-09:oee-up")
		self.assertIn("7.0 points", out[0]["message"])

	def test_small_gain_or_a_drop_says_nothing(self):
		self.assertEqual(self.codes(week(68), [week(65)]), [])
		self.assertEqual(self.codes(week(50), [week(65)]), [])

	def test_best_week_needs_enough_history(self):
		history = [week(60), week(62), week(61)]
		self.assertNotIn("best-week", self.codes(week(64), history))
		self.assertIn("best-week", self.codes(week(64), [*history, week(63)]))
		self.assertNotIn("best-week", self.codes(week(64), [*history, week(66)]))

	def test_thin_weeks_say_nothing(self):
		self.assertEqual(self.codes(week(90, planned=60, scrap=0), [week(40)]), [])

	def test_previous_week_skips_thin_weeks(self):
		# The comparison is with the last week that had enough planned time.
		self.assertEqual(self.codes(week(72), [week(10, planned=30), week(65)]), ["oee-up"])

	def test_zero_scrap(self):
		self.assertEqual(self.codes(week(60, scrap=0), []), ["zero-scrap"])
		self.assertEqual(self.codes(week(60, good=0, scrap=0), []), [])

	def test_quality_up(self):
		this = {**week(60), "quality": 99.0}
		self.assertEqual(self.codes(this, [{**week(60), "quality": 97.5}]), ["quality-up"])
		self.assertEqual(self.codes(this, [{**week(60), "quality": 98.5}]), [])

	def test_andon_on_target(self):
		self.assertEqual(self.codes(week(None), [], {"calls": 4, "on_target": 4}), ["andon-on-target"])
		self.assertEqual(self.codes(week(None), [], {"calls": 4, "on_target": 3}), [])
		self.assertEqual(self.codes(week(None), [], {"calls": 2, "on_target": 2}), [])


class TestFloorItems(unittest.TestCase):
	rows = (
		{
			"name": "REC-1",
			"kind": "Kudos",
			"recipient_type": "Person",
			"recipient": "ana@x",
			"team": "Line 1",
			"message": "Caught the bad batch",
			"given_by": "bo@x",
		},
		{"name": "REC-2", "kind": "Kudos", "recipient_type": "Person", "recipient": "cy@x", "message": "x"},
		{"name": "REC-3", "kind": "Kudos", "recipient_type": "Person", "recipient": "di@x", "private": 1},
		{
			"name": "REC-4",
			"kind": "Kudos",
			"recipient_type": "Person",
			"recipient": "ed@x",
			"status": "Withdrawn",
		},
		{
			"name": "REC-5",
			"kind": "Team Highlight",
			"recipient_type": "Team",
			"team": "Line 2",
			"message": "y",
		},
	)

	def test_names_shown(self):
		out = floor_items(self.rows, full_names={"ana@x": "Ana", "bo@x": "Bo"})
		self.assertEqual([i["name"] for i in out], ["REC-1", "REC-2", "REC-5"])
		self.assertEqual((out[0]["recipient"], out[0]["from"]), ("Ana", "Bo"))
		self.assertEqual(out[1]["recipient"], "cy@x")
		self.assertEqual(out[2]["recipient"], "Line 2")

	def test_opted_out_people_are_left_out(self):
		out = floor_items(self.rows, opted_out={"ana@x"})
		self.assertEqual([i["name"] for i in out], ["REC-2", "REC-5"])

	def test_names_hidden(self):
		out = floor_items(self.rows, show_names=False)
		self.assertEqual(
			[(i["recipient"], i["from"]) for i in out],
			[("Line 1", None), ("A teammate", None), ("Line 2", None)],
		)


if __name__ == "__main__":
	unittest.main()
