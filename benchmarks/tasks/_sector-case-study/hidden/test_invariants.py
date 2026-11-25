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

"""FoaMES's rules, checked by running the agent's script on data it has not seen: silence stays
Unknown, a reset or a late or repeated reading adds nothing, a meter's rollover is unwrapped, and
the answers come from the script and the data rather than being typed in."""

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_compare", Path(__file__).with_name("_compare.py"))
cmp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmp)


def _variant(**traps):
	"""The task's sector, reseeded, with other planted conditions and no energy calibration."""
	return cmp._fixture.variant(cmp.SECTOR, seed=cmp.SECTOR["seed"] + 1000, target_ratio=None, traps=traps)


class TestRules(unittest.TestCase):
	def _run(self, sector):
		with tempfile.TemporaryDirectory() as tmp:
			data = Path(tmp) / "case"
			cmp._fixture.write(sector, data)
			got = cmp.run_script(data, Path(tmp) / "out.json")
		self.assertEqual(cmp.differences(got, cmp.expected(sector)), [])
		return got

	def test_ledger_accounts_for_every_planned_minute(self):
		got = cmp.committed()
		for window in ("baseline", "after"):
			w = got["windows"][window]
			accounted = sum(float(w[f]) for f in cmp.LEDGER_FIELDS)
			self.assertAlmostEqual(accounted, float(w["planned_minutes"]), delta=0.1, msg=window)

	def test_gateway_silence_stays_unknown(self):
		got = self._run(_variant(network_gap={"window": "baseline", "at": 0.3, "hours": 6}))
		self.assertGreater(float(got["windows"]["baseline"]["unknown_minutes"]), 60)

	def test_plc_reset_adds_nothing(self):
		self._run(_variant(plc_reset={"window": "baseline", "at": 0.55}))

	def test_late_and_repeated_readings_add_nothing(self):
		self._run(
			_variant(
				out_of_order={"window": "after", "arrives_after": 9},
				duplicate={"window": "baseline"},
			)
		)

	def test_meter_rollover_is_unwrapped(self):
		sector = _variant(meter_rollover={"window": "after", "at": 0.45})
		sector["meter"]["rollover"] = sector["meter"].get("rollover") or 1_000_000
		self._run(sector)

	def test_script_regenerates_the_committed_answers(self):
		with tempfile.TemporaryDirectory() as tmp:
			got = cmp.run_script(cmp.WORKSPACE / "data" / "case", Path(tmp) / "out.json")
		self.assertEqual(cmp.differences(got, cmp.committed()), [])

	def test_inputs_and_foames_untouched(self):
		result = subprocess.run(
			["git", "diff", "--name-only", "task-start", "--", "data", "foames"],
			cwd=cmp.WORKSPACE,
			capture_output=True,
			text=True,
		)
		self.assertEqual(result.stdout.strip(), "")
