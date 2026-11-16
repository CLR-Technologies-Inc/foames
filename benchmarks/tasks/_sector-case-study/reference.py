# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Reference solution for every sector case study: a script on FoaMES's own counter and OEE code,
a unit test for it, the case study write-up and the notes."""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

TEST = """import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("case_study", Path(__file__).with_name("case_study.py"))
case_study = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(case_study)

CASE = {
	"planned_hours": [[0, 24]],
	"planned_weekdays": [0, 1, 2, 3, 4, 5, 6],
	"mark_unknown_after_minutes": 30,
	"machines": [{"source_id": "L", "role": "line", "counter_rollover": None}],
}


def row(seq, ts, kind, state="", value=""):
	return {"seq": str(seq), "source_id": "L", "timestamp": ts, "event_type": kind, "state": state,
		"planned": "0", "counter_name": "good" if kind == "Count" else "", "counter_value": str(value)}


class TestCaseStudy(unittest.TestCase):
	def test_reset_and_late_reading_count_nothing(self):
		rows = [row(1, "2026-01-05T00:00:00Z", "Count", value=100), row(2, "2026-01-05T00:15:00Z", "Count", value=150),
			row(3, "2026-01-05T00:30:00Z", "Count", value=0), row(4, "2026-01-05T00:45:00Z", "Count", value=20),
			row(5, "2026-01-05T00:20:00Z", "Count", value=160)]
		self.assertEqual([d[3] for d in case_study.counter_deltas(CASE, rows)], [0.0, 50.0, 0.0, 20.0, 0.0])

	def test_silence_is_unknown(self):
		rows = [row(1, "2026-01-05T00:00:00Z", "State", state="Running"), row(2, "2026-01-05T02:00:00Z", "State", state="Running")]
		start, end = datetime(2026, 1, 5, tzinfo=timezone.utc), datetime(2026, 1, 5, 3, tzinfo=timezone.utc)
		book, _ = case_study.ledger(CASE, rows, "L", start, end)
		self.assertAlmostEqual(book.run_minutes, 60.0)
		self.assertAlmostEqual(book.unknown_minutes, 120.0)
		self.assertAlmostEqual(book.accounted_minutes, book.planned_minutes)


if __name__ == "__main__":
	unittest.main()
"""


def _fmt(value, digits=3):
	if value is None:
		return "n/a"
	if isinstance(value, float):
		return f"{value:,.{digits}f}"
	return str(value)


def _write_case_study(workspace: Path, case: dict, result: dict):
	b, a = result["windows"]["baseline"], result["windows"]["after"]
	check = result["claim_check"]
	src = case["source"]
	rows = [
		("Good output (" + case["production_unit"] + ")", "good"),
		("Scrap (" + case["production_unit"] + ")", "scrap"),
		("Energy (" + case["energy_unit"] + ")", "energy"),
		(
			"Specific energy (" + case["energy_unit"] + " per " + case["production_unit"] + ")",
			"specific_energy",
		),
		("Availability", "availability"),
		("OEE", "oee"),
		("Good per planned hour", "good_per_planned_hour"),
		("Mean setup minutes", "mean_setup_minutes"),
		("Unknown minutes (counted as loss)", "unknown_minutes"),
	]
	table = "\n".join(
		f"| {label} | {_fmt(b[k])} | {_fmt(a[k])} | `case_study.json` windows.*.{k} |" for label, k in rows
	)
	text = f"""# Case study: {case["sector"]}

| | |
| --- | --- |
| Status | Draft |
| Data | Illustrative. Synthetic FoaMES events grounded in the figures of the cited source; not measured at any plant |
| Segment | NAICS {case["naics"]} |
| Plant | {case["plant"]} |
| Period | Baseline: {case["windows"]["baseline"]["start"]} to {case["windows"]["baseline"]["end"]}. After: {case["windows"]["after"]["start"]} to {case["windows"]["after"]["end"]} |

## 1. Summary

The source reports: {case["claim"]["text"]} Measured from the FoaMES events, the claim check is **{check["verdict"]}** (measured {_fmt(check["measured"])} against {_fmt(check["claimed"])} claimed, ratio {_fmt(check["ratio"])}). This is an illustrative reconstruction, so it says how the claim would be checked, not whether the original plant achieved it.

## 2. Context

{case["plant"]} stands in for the plant in the source. Its line `{case["machines"][0]["source_id"]}` and meter `{case["machines"][1]["source_id"]}` report state and running-total counters to FoaMES.

## 3. The improvement

As described in the source; no figure here is a vendor claim. The source's figure is a claim to verify, and the measured result is reported next to it, not in place of it.

## 4. Measurement design

Production and energy are summed from counter deltas: a first reading, a reset or an out-of-order reading counts zero, and the meter's rollover is applied. Time without a machine signal for longer than {case["mark_unknown_after_minutes"]} minutes is Unknown and stays loss in both windows. Specific energy is energy per good unit, so base load is spread over output: a change in production volume moves it as well.

## 5. Data connection

A gateway sends state changes and counter readings. Silent periods are kept as Unknown, never filled with the last state.

## 6. Results

| Metric | Baseline | After | Evidence |
| --- | --- | --- | --- |
{table}

Annualised energy saving: {_fmt(result["annual_energy_saving"])} {case["energy_unit"]} per year; cost {_fmt(result["annual_cost_saving"], 0)} at the case's energy price. FoaMES suggests; the people who own the line act on it.

## 7. What else changed

Production volume and mix, unplanned downtime and the unknown time differ between windows. Each one moves specific energy or OEE independently of the improvement.

## 8. Gaps

The events cannot show lead time, work in progress, labour or maintenance cost; figures of that kind in the source cannot be verified from them.

## 9. Lessons and next steps

Replace the illustrative events with measured data from a connected plant before publishing as a result.

## Sources

- {src["publisher"]}, "{src["title"]}", {src.get("report", "")}, {src.get("date", "")}. {src["url"]}. A US government work; only its figures are used, no text or images.
"""
	(workspace / "CASE_STUDY.md").write_text(text, encoding="utf-8")


def apply(workspace: Path):
	(workspace / "analysis").mkdir(exist_ok=True)
	(workspace / "analysis" / "case_study.py").write_text(
		(HERE / "solution_case_study.py").read_text(encoding="utf-8"), encoding="utf-8"
	)
	(workspace / "analysis" / "test_case_study.py").write_text(TEST, encoding="utf-8")
	env = {
		**os.environ,
		"PYTHONPATH": os.pathsep.join([str(workspace / ".foames-bench" / "stubs"), str(workspace)]),
	}
	subprocess.run([sys.executable, "analysis/case_study.py"], cwd=workspace, env=env, check=True)
	case = json.loads((workspace / "data" / "case" / "case.json").read_text(encoding="utf-8"))
	result = json.loads((workspace / "case_study.json").read_text(encoding="utf-8"))
	_write_case_study(workspace, case, result)
	(workspace / "BENCH_NOTES.md").write_text(
		"Reference solution. analysis/case_study.py takes counter deltas from "
		"foames.foames_mes.counters.counter_delta, compared with the latest reading by timestamp as the "
		"Machine Event DocType does, so the PLC reset, the duplicate and the late reading add nothing and "
		"the meter's rollover is unwrapped. The ledger keeps the gateway's silence as Unknown, which "
		"counts as loss, and OEE comes from foames.foames_mes.oee.compute_oee. The source's figure is "
		"reported as a claim next to the measured value. The data is illustrative and cannot show lead "
		"time, labour or why production volume changed between the windows.\n",
		encoding="utf-8",
	)
