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

"""The numbers in case_study.json against an independent computation from the pristine data."""

import importlib.util
import re
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_compare", Path(__file__).with_name("_compare.py"))
cmp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmp)

WANT = cmp.expected()


class TestCaseStudyNumbers(unittest.TestCase):
	def setUp(self):
		self.got = cmp.committed()

	def _check(self, fields):
		problems = []
		for window in ("baseline", "after"):
			got = (self.got.get("windows") or {}).get(window) or {}
			for field in fields:
				p = cmp.close(got.get(field), WANT["windows"][window][field], f"{window}.{field}")
				if p:
					problems.append(p)
		self.assertEqual(problems, [])

	def test_case_id(self):
		self.assertEqual(self.got.get("case_id"), WANT["case_id"])

	def test_planned_time(self):
		self._check(["planned_minutes"])

	def test_time_ledger(self):
		self._check(cmp.LEDGER_FIELDS)

	def test_production(self):
		self._check(["good", "scrap"])

	def test_energy(self):
		self._check(["energy", "specific_energy"])

	def test_oee(self):
		self._check(["availability", "performance", "quality", "oee"])

	def test_throughput_and_changeovers(self):
		self._check(["good_per_planned_hour", "changeovers", "mean_setup_minutes"])

	def test_annual_saving(self):
		for field in ("annual_energy_saving", "annual_cost_saving"):
			self.assertIsNone(cmp.close(self.got.get(field), WANT[field], field))

	def test_claim_check(self):
		check = self.got.get("claim_check") or {}
		self.assertEqual(check.get("kind"), WANT["claim_check"]["kind"])
		for field in ("claimed", "measured", "ratio"):
			self.assertIsNone(cmp.close(check.get(field), WANT["claim_check"][field], field))
		self.assertEqual(check.get("verdict"), WANT["claim_check"]["verdict"])


class TestCaseStudyWriteUp(unittest.TestCase):
	def setUp(self):
		path = cmp.WORKSPACE / "CASE_STUDY.md"
		self.text = path.read_text(encoding="utf-8") if path.exists() else ""

	def test_cites_the_source(self):
		self.assertIn(cmp.SECTOR["source"]["url"], self.text)

	def test_labelled_illustrative(self):
		self.assertRegex(self.text, r"(?i)illustrative")

	def test_states_the_verdict(self):
		verdict = WANT["claim_check"]["verdict"]
		pattern = r"(?<!not )supported" if verdict == "supported" else re.escape(verdict)
		self.assertRegex(self.text.lower(), pattern)

	def test_plant_is_anonymised(self):
		"""The study is about Plant A, not about the company the source names."""
		for name in cmp.SECTOR["source"].get("named_organisations", []):
			lines = [l for l in self.text.splitlines() if re.search(re.escape(name), l, re.IGNORECASE)]
			# A name may appear in the citation of the source, nowhere else.
			self.assertTrue(all(cmp.SECTOR["source"]["url"] in l or "Sources" in l for l in lines), lines)
