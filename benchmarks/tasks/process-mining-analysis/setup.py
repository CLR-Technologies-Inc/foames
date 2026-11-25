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

"""Write the synthetic event log into the workspace."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("pm_fixture", Path(__file__).with_name("fixture.py"))
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def setup(workspace: Path):
	target = workspace / "data" / "weld_cell_events.csv"
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(fixture.to_csv(fixture.rows()), encoding="utf-8")
