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

"""Shared helpers for the sector case study tests: the sector, the reference result and a
tolerant comparison."""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
	sys.path.insert(0, str(HERE))

import _fixture
import _mv_reference

WORKSPACE = Path(os.environ["FOAMES_BENCH_WORKSPACE"])
SECTOR = _fixture.load_sector(HERE / "sector.json")
WINDOW_FIELDS = (
	"planned_minutes",
	"run_minutes",
	"idle_minutes",
	"setup_minutes",
	"planned_downtime_minutes",
	"unplanned_downtime_minutes",
	"unknown_minutes",
	"good",
	"scrap",
	"energy",
	"availability",
	"performance",
	"quality",
	"oee",
	"specific_energy",
	"good_per_planned_hour",
	"changeovers",
	"mean_setup_minutes",
)
LEDGER_FIELDS = WINDOW_FIELDS[1:7]


def expected(sector=SECTOR) -> dict:
	rows = _fixture.parse_rows(_fixture.to_csv(_fixture.events(sector)))
	return _mv_reference.analyse(_fixture.case_json(sector), rows)


def committed() -> dict:
	return json.loads((WORKSPACE / "case_study.json").read_text(encoding="utf-8"))


def close(got, want, field="") -> str | None:
	"""None when got matches want, else why not. Minutes to 0.05, everything else to 0.01 percent."""
	if want is None or got is None:
		return None if got is want else f"{field}: got {got!r}, expected {want!r}"
	if isinstance(want, str):
		return None if got == want else f"{field}: got {got!r}, expected {want!r}"
	try:
		got = float(got)
	except (TypeError, ValueError):
		return f"{field}: got {got!r}, expected a number near {want!r}"
	tolerance = 0.05 if field.endswith("minutes") else max(abs(want) * 1e-4, 1e-6)
	return None if abs(got - want) <= tolerance else f"{field}: got {got}, expected {want}"


def differences(got: dict, want: dict) -> list[str]:
	out = []
	for window in ("baseline", "after"):
		g = (got.get("windows") or {}).get(window) or {}
		for field in WINDOW_FIELDS:
			problem = close(g.get(field), want["windows"][window][field], f"{window}.{field}")
			if problem:
				out.append(problem)
	for field in ("annual_energy_saving", "annual_cost_saving"):
		problem = close(got.get(field), want[field], field)
		if problem:
			out.append(problem)
	check = got.get("claim_check") or {}
	for field in ("measured", "ratio", "verdict"):
		problem = close(check.get(field), want["claim_check"][field], f"claim_check.{field}")
		if problem:
			out.append(problem)
	return out


def run_script(data_dir: Path, out: Path) -> dict:
	"""Run the agent's script on other data, from the workspace, the way the prompt says."""
	env = {
		**os.environ,
		"PYTHONPATH": os.pathsep.join([str(WORKSPACE / ".foames-bench" / "stubs"), str(WORKSPACE)]),
	}
	subprocess.run(
		[sys.executable, "analysis/case_study.py", "--data", str(data_dir), "--out", str(out)],
		cwd=WORKSPACE,
		env=env,
		check=True,
		capture_output=True,
		timeout=300,
	)
	return json.loads(out.read_text(encoding="utf-8"))
