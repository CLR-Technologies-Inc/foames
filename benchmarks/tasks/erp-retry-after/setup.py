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

"""Plant the defect: a server error on a posting is retried blind instead of being checked first,
so a 5xx that came after S/4HANA committed the posting produces a duplicate."""

from pathlib import Path

ORIGINAL = """		return Outcome(
			"Unknown" if e.maybe_applied or verify_first else "Retry", error=str(e), details=e.details
		)"""
DEFECT = """		return Outcome("Retry", error=str(e), details=e.details)"""


def setup(workspace: Path):
	path = workspace / "foames" / "foames_adapters" / "s4hana" / "outbox.py"
	text = path.read_text(encoding="utf-8")
	assert ORIGINAL in text, "outbox.py changed upstream; update the task setup"
	path.write_text(text.replace(ORIGINAL, DEFECT), encoding="utf-8")
