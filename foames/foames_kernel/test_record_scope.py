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

"""The pure record-scope rules: no site needed.

python -m unittest foames.foames_kernel.test_record_scope
"""

import unittest
from typing import ClassVar

from foames.foames_kernel import record_scope as s


class TestRowScope(unittest.TestCase):
	def test_a_row_names_its_machine_directly_or_by_reference(self):
		self.assertEqual(s.row_machine({"machine": "M-1"}), "M-1")
		self.assertEqual(s.row_machine({"reference_doctype": "Machine", "reference_name": "M-2"}), "M-2")
		self.assertEqual(s.row_machine({"subject_type": "Machine", "subject": "M-3"}), "M-3")
		self.assertIsNone(s.row_machine({"reference_doctype": "Work Order", "reference_name": "M-2"}))
		self.assertIsNone(s.row_machine({"subject_type": "Process", "subject": "Fill"}))

	def test_no_restriction_keeps_everything(self):
		rows = [{"machine": "M-1"}, {"machine": "M-9"}]
		self.assertEqual(s.filter_rows(rows, None), rows)

	def test_rows_about_other_machines_are_dropped(self):
		rows = [{"machine": "M-1"}, {"machine": "M-9"}, {"title": "site-wide"}]
		self.assertEqual(s.filter_rows(rows, {"M-1"}), [{"machine": "M-1"}, {"title": "site-wide"}])

	def test_an_empty_scope_shows_no_machine(self):
		self.assertEqual(s.filter_rows([{"machine": "M-1"}], set()), [])


class TestScrub(unittest.TestCase):
	def test_nested_sections_are_scrubbed(self):
		snapshot = {
			"machines": [{"name": "M-1", "andon": [{"machine": "M-1"}]}],
			"extension": {"alarms": [{"machine": "M-9", "text": "hidden"}, {"machine": "M-1"}]},
			"open_suggestions": [
				{"reference_doctype": "Machine", "reference_name": "M-9"},
				{"reference_doctype": "Machine", "reference_name": "M-1"},
			],
			"as_of": "now",
		}
		out = s.scrub(snapshot, {"M-1"})
		self.assertEqual(out["extension"]["alarms"], [{"machine": "M-1"}])
		self.assertEqual(out["open_suggestions"], [{"reference_doctype": "Machine", "reference_name": "M-1"}])
		self.assertEqual(out["machines"][0]["andon"], [{"machine": "M-1"}])
		self.assertEqual(out["as_of"], "now")

	def test_a_record_held_as_a_dict_value_is_dropped(self):
		out = s.scrub({"latest": {"machine": "M-9", "text": "hidden"}, "mine": {"machine": "M-1"}}, {"M-1"})
		self.assertEqual(out, {"mine": {"machine": "M-1"}})

	def test_scrub_keeps_the_mapping_class(self):
		class AttrDict(dict):
			__getattr__ = dict.get

		out = s.scrub({"machines": [AttrDict(name="M-1")]}, {"M-1"})
		self.assertEqual(out["machines"][0].name, "M-1")

	def test_scrub_without_restriction_is_identity(self):
		value = {"a": [{"machine": "M-9"}]}
		self.assertIs(s.scrub(value, None), value)

	def test_projection_keeps_only_named_fields(self):
		self.assertEqual(s.project({"a": 1, "b": 2, "c": 3}, ["a", "c"]), {"a": 1, "c": 3})


class TestPolicyLoosening(unittest.TestCase):
	BASE: ClassVar[dict] = {
		"read_only": 1,
		"when_read_only": "Queue for sign-off",
		"sign_off_role": "FoaMES Supervisor",
	}

	def after(self, **changes):
		return {**self.BASE, **changes}

	def test_unchanged_or_tightened_is_not_loosening(self):
		self.assertEqual(s.policy_loosening(self.BASE, self.after()), [])
		self.assertEqual(s.policy_loosening(self.BASE, self.after(when_read_only="Block")), [])
		self.assertEqual(
			s.policy_loosening(self.after(read_only=0), self.after(read_only=1)),
			[],
		)

	def test_turning_read_only_off_loosens(self):
		self.assertEqual(s.policy_loosening(self.BASE, self.after(read_only=0)), ["read-only turned off"])

	def test_a_less_strict_choice_loosens(self):
		before = self.after(when_read_only="Block")
		self.assertTrue(s.policy_loosening(before, self.after(when_read_only="Site default")))
		self.assertTrue(
			s.policy_loosening(
				self.after(when_read_only="Site default"), self.after(when_read_only="Queue for sign-off")
			)
		)

	def test_changing_who_signs_off_loosens(self):
		self.assertEqual(
			s.policy_loosening(self.BASE, self.after(sign_off_role="FoaMES Operator")),
			["sign-off role changed"],
		)

	def test_a_new_policy_is_judged_against_the_site_defaults(self):
		self.assertTrue(s.policy_loosening(None, self.after(read_only=0)))
		inherit = {"read_only": 1, "when_read_only": "Site default", "sign_off_role": ""}
		self.assertEqual(s.policy_loosening(None, inherit), [])
		self.assertEqual(s.policy_loosening(None, {**inherit, "when_read_only": "Block"}), [])
		# Overriding the site's action or sign-off role weakens what the connector inherits.
		self.assertTrue(s.policy_loosening(None, {**inherit, "when_read_only": "Queue for sign-off"}))
		self.assertTrue(s.policy_loosening(None, {**inherit, "sign_off_role": "FoaMES Engineer"}))


if __name__ == "__main__":
	unittest.main()
