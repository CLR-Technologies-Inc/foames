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

"""Reference solution for process-mining-analysis: FoaMES's own process-mining module."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = '''"""Answers about the welding cell from data/weld_cell_events.csv, using FoaMES process mining."""

import csv
import json
from pathlib import Path
from statistics import median

from foames.foames_process_mining import discovery
from foames.foames_process_mining.eventlog import Event, EventLog, parse_timestamp

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "data" / "weld_cell_events.csv", newline="", encoding="utf-8") as f:
	log = EventLog(
		Event(r["case_id"], r["activity"], parse_timestamp(r["timestamp"]), r["resource"], r["lifecycle"])
		for r in csv.DictReader(f)
	)

variants = log.variants()
top, top_cases = next(iter(variants.items()))
traces = log.traces()
answers = {
	"cases": len(traces),
	"variants": len(variants),
	"top_variant": {"activities": list(top), "cases": len(top_cases)},
	"median_cycle_time_minutes": round(median(discovery.case_durations(log).values()) / 60, 2),
	"rework_cases": discovery.rework(log),
	"bottleneck": discovery.bottlenecks(log, 1)[0]["activity"],
	"incomplete_cases": sorted(c for c, ev in traces.items() if not any(e.activity == "Pack" for e in ev)),
}
(ROOT / "answers.json").write_text(json.dumps(answers, indent=1) + "\\n", encoding="utf-8")
'''


def apply(workspace: Path):
	(workspace / "analysis").mkdir(exist_ok=True)
	(workspace / "analysis" / "analyze.py").write_text(SCRIPT, encoding="utf-8")
	env = {
		**os.environ,
		"PYTHONPATH": os.pathsep.join([str(workspace / ".foames-bench" / "stubs"), str(workspace)]),
	}
	subprocess.run([sys.executable, "analysis/analyze.py"], cwd=workspace, env=env, check=True)
	(workspace / "BENCH_NOTES.md").write_text(
		"Reference solution. analysis/analyze.py loads the export into a FoaMES EventLog (which sorts it), "
		"and takes variants, case durations, rework and waiting-time bottlenecks from "
		"foames.foames_process_mining.discovery. Three work orders never reached Pack; their cycle times "
		"are only lower bounds, and they are included in the median as the request asks. The export cannot "
		"say why Inspect queues: QC staffing and batching are the first things to check with people.\n",
		encoding="utf-8",
	)
