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

"""Tests for the Equipment Complexity Level rules. No site is needed:

python -m unittest foames.foames_mes.test_ecl
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from foames.foames_mes import ecl

RECOMMENDATIONS = Path(__file__).resolve().parents[2] / "benchmarks" / "data" / "recommendations.json"


class TestLevels(unittest.TestCase):
	def test_parse(self):
		self.assertIsNone(ecl.parse_ecl(""))
		self.assertIsNone(ecl.parse_ecl(None))
		self.assertEqual(ecl.parse_ecl("3"), 3)
		self.assertEqual(ecl.parse_ecl(5), 5)
		for bad in ("6", "x", -1):
			with self.assertRaises(ValueError):
				ecl.parse_ecl(bad)

	def test_oversight_grows_with_level(self):
		self.assertEqual([ecl.LEVELS[n]["oversight"] for n in range(1, 6)], ["none"] * 3 + ["single", "team"])
		self.assertEqual(ecl.profile(4)["human_oversight"], "Human Expert Recommended")
		self.assertEqual(ecl.profile(5)["human_oversight"], "Expert Team Required")
		self.assertFalse(ecl.profile(5)["agents_allowed"])
		self.assertFalse(ecl.profile(None)["rated"])

	def test_agent_never_above_loa_4(self):
		loas = [ecl.LEVELS[n]["loa"] for n in range(1, 6)]
		self.assertTrue(all(loa <= 4 for loa in loas))
		self.assertEqual(loas, sorted(loas, reverse=True))

	@unittest.skipUnless(RECOMMENDATIONS.exists(), "benchmarks/ is not next to the app")
	def test_matches_the_benchmark(self):
		levels = json.loads(RECOMMENDATIONS.read_text())["ecl"]["levels"]
		for number, info in ecl.LEVELS.items():
			bench = levels[str(number)]
			self.assertEqual(info["min_tier"], bench["min_tier"], number)
			self.assertEqual(info["name"], bench["name"], number)
			self.assertEqual(info["oversight"] != "none", bench["human_expert_recommended"], number)
			self.assertEqual(ecl.OVERSIGHT_LABELS[info["oversight"]], bench.get("human_oversight"), number)
			self.assertTrue(bench["agent_role"].startswith(f"LOA {info['loa']}"), number)


class TestEligibility(unittest.TestCase):
	def test_tier_meets_the_floor(self):
		self.assertTrue(ecl.eligibility("oss", 1)["eligible"])
		self.assertFalse(ecl.eligibility("oss", 3)["eligible"])
		self.assertTrue(ecl.eligibility("frontier", 3)["eligible"])

	def test_expert_stays_in_charge(self):
		result = ecl.eligibility("frontier", 4)
		self.assertTrue(result["eligible"])
		self.assertEqual(result["oversight"], "single")
		self.assertIn("Human Expert Recommended", result["reason"])

	def test_nothing_qualifies_at_5(self):
		result = ecl.eligibility("frontier", 5)
		self.assertFalse(result["eligible"])
		self.assertIn("Expert Team Required", result["reason"])

	def test_unrated_never_qualifies(self):
		self.assertFalse(ecl.eligibility("frontier", None)["eligible"])

	def test_no_tier_given(self):
		self.assertIsNone(ecl.eligibility(None, 2)["eligible"])

	def test_unknown_tier(self):
		with self.assertRaises(ValueError):
			ecl.eligibility("huge", 2)


class TestGroupsAndMaterial(unittest.TestCase):
	def test_line_takes_its_most_complex_member(self):
		self.assertEqual(ecl.group_ecl(["2", "", "4", None, 3]), 4)
		self.assertIsNone(ecl.group_ecl(["", None]))

	def test_combined_oversight(self):
		self.assertEqual(ecl.combined_oversight("none", "single"), "single")
		self.assertEqual(ecl.combined_oversight("single", "team", None), "team")
		self.assertEqual(ecl.combined_oversight(), "none")

	def test_mpc_follows_the_same_pattern(self):
		self.assertEqual([ecl.mpc_oversight(n) for n in range(1, 6)], ["none"] * 3 + ["single", "team"])
		self.assertEqual(ecl.mpc_oversight(None), "none")
		self.assertEqual(ecl.combined_oversight(ecl.profile(2)["oversight"], ecl.mpc_oversight(5)), "team")


class TestPublicList(unittest.TestCase):
	def test_class_ids(self):
		self.assertTrue(ecl.valid_class_id("cnc-machining-centre"))
		for bad in ("", None, "CNC", "two words", "-x", "x-"):
			self.assertFalse(ecl.valid_class_id(bad), bad)

	def test_rating_from_an_ai_initial_entry_is_a_draft(self):
		entry = {
			"id": "torque-wrench",
			"name": "Torque wrench",
			"ecl": 1,
			"ecl_rationale": "Torque is force times lever arm.",
			"confidence": "high",
			"reviewed_by": "ai-initial",
		}
		rating = ecl.rating_from_class(entry)
		self.assertEqual(rating["ecl"], 1)
		self.assertTrue(rating["draft"])
		self.assertEqual(rating["ecl_class"], "torque-wrench")
		reviewed = ecl.rating_from_class({**entry, "reviewed_by": "someone"})
		self.assertFalse(reviewed["draft"])
		with self.assertRaises(ValueError):
			ecl.rating_from_class({"id": "x"})


if __name__ == "__main__":
	unittest.main()
