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

"""Reference solution: restore the reset rule and add a regression test."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("counter_reset_setup", Path(__file__).with_name("setup.py"))
_setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_setup)

TEST = """import unittest

from foames.foames_mes.counters import counter_delta


class TestCounterReset(unittest.TestCase):
	def test_reset_counts_nothing(self):
		self.assertEqual(counter_delta(48112, 0), 0.0)
		self.assertEqual(counter_delta(48112, 37), 0.0)

	def test_known_rollover_still_wraps(self):
		self.assertEqual(counter_delta(65530, 4, rollover=65535), 9.0)
"""


def apply(workspace: Path):
	path = workspace / "foames" / "foames_mes" / "counters.py"
	path.write_text(
		path.read_text(encoding="utf-8").replace(_setup.DEFECT, _setup.ORIGINAL), encoding="utf-8"
	)
	(workspace / "foames" / "foames_mes" / "test_counter_reset.py").write_text(TEST, encoding="utf-8")
	(workspace / "BENCH_NOTES.md").write_text(
		"Reference solution. counter_delta treated a drop in the running total as a new count from zero, "
		"so the restart added the post-restart total as production. A drop is now a reset or an out-of-order "
		"reading and yields zero, as AGENTS.md invariant 3 says; a wrap is counted only when the rollover is "
		"known. The parts made between the restart and the next reading cannot be recovered from the counter "
		"alone and are not invented.\n",
		encoding="utf-8",
	)
