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

"""Where the benchmark, its tasks and the FoaMES checkout under test live."""

import os
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = BENCH_ROOT / "tasks"
DATA_DIR = BENCH_ROOT / "data"
STUBS_DIR = Path(__file__).resolve().parent / "stubs"


def repo_root(override: str | None = None) -> Path:
	"""The FoaMES checkout whose code the tasks start from: --repo, $FOAMES_REPO, or the parent of
	benchmarks/ when the benchmark sits inside a FoaMES clone."""
	candidate = override or os.environ.get("FOAMES_REPO") or str(BENCH_ROOT.parent)
	root = Path(candidate).expanduser().resolve()
	if not (root / "foames" / "hooks.py").exists():
		raise SystemExit(f"{root} is not a FoaMES checkout (no foames/hooks.py); pass --repo")
	return root
