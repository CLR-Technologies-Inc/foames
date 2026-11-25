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

"""Plant the defect: a counter that drops is taken as a fresh count from zero, so a reset or an
out-of-order reading invents production."""

from pathlib import Path

ORIGINAL = """	# A reset or an out-of-order reading. Nothing is invented.
	return 0.0
"""
DEFECT = """	# The counter restarted from zero: count what it has made since.
	return float(current)
"""


def setup(workspace: Path):
	path = workspace / "foames" / "foames_mes" / "counters.py"
	text = path.read_text(encoding="utf-8")
	assert ORIGINAL in text, "counters.py changed upstream; update the task setup"
	path.write_text(text.replace(ORIGINAL, DEFECT), encoding="utf-8")
