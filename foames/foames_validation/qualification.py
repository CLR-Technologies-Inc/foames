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

"""Qualification and validation rules. No Frappe dependency.

Follows the life-cycle approach to process validation that regulators and standards bodies publish
(the US FDA's 2011 "Process Validation: General Principles and Practices", the GHTF SG3/N99-10 process
validation guidance, EU GMP Annex 15):

- Stage 1, process design, happens before anything here.
- Stage 2, process qualification: installation (IQ), operational (OQ) and performance (PQ)
  qualification of the equipment, then process performance qualification (PPQ), usually a number
  of consecutive passing runs.
- Stage 3, continued process verification (CPV): the process is shown to stay in a state of control.

A protocol is approved before it is executed. An execution records a result for every acceptance
criterion; a criterion that fails needs a documented deviation, and a critical one cannot be
accepted by deviation. Qualification lapses after the protocol's validity period, so equipment and
processes are requalified on a schedule.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, datetime, timedelta

from foames.foames_mes import spc

# code -> (name, validation stage, prerequisite code, default number of consecutive runs)
PROTOCOL_TYPES = {
	"IQ": ("Installation Qualification", "Stage 2: Process Qualification", None, 1),
	"OQ": ("Operational Qualification", "Stage 2: Process Qualification", "IQ", 1),
	"PQ": ("Performance Qualification", "Stage 2: Process Qualification", "OQ", 1),
	"PPQ": ("Process Performance Qualification", "Stage 2: Process Qualification", "PQ", 3),
	"CPV": ("Continued Process Verification", "Stage 3: Continued Process Verification", "PPQ", 1),
}
EQUIPMENT_TYPES = ("IQ", "OQ", "PQ")
PROCESS_TYPES = ("PPQ", "CPV")

CHECK_TYPES = ("Pass/Fail", "Numeric Range", "Capability", "Statistical Control")
MACHINE_DATA_TYPES = ("Capability", "Statistical Control")
DEFAULT_MIN_INDEX = 1.33
DEFAULT_MIN_POINTS = 25

PASS, FAIL, PENDING, NA = "Pass", "Fail", "Pending", "N/A"
PASSED, PASSED_WITH_DEVIATIONS, FAILED, INCOMPLETE = (
	"Passed",
	"Passed with Deviations",
	"Failed",
	"Incomplete",
)
ACCEPT_DEVIATION = "Accepted: no impact on the conclusion"
REJECT_DEVIATION = "Rejected: the criterion is not met"
DISPOSITIONS = (ACCEPT_DEVIATION, REJECT_DEVIATION)

QUALIFIED, DUE_SOON, EXPIRED, NOT_QUALIFIED, RUNS_PENDING = (
	"Qualified",
	"Due Soon",
	"Expired",
	"Not Qualified",
	"Runs Pending",
)
CURRENT = (QUALIFIED, DUE_SOON)
DEFAULT_DUE_SOON_DAYS = 30


def protocol_type(code: str) -> dict:
	if code not in PROTOCOL_TYPES:
		raise ValueError(f"unknown protocol type {code!r}; use one of {', '.join(PROTOCOL_TYPES)}")
	name, stage, prerequisite, runs = PROTOCOL_TYPES[code]
	return {"code": code, "name": name, "stage": stage, "prerequisite": prerequisite, "default_runs": runs}


# --------------------------------------------------------------------- criteria


def _num(x):
	if x is None or x == "":
		return None
	x = float(x)
	return None if math.isnan(x) else x


def _within(value, lower, upper) -> bool:
	return (lower is None or value >= lower) and (upper is None or value <= upper)


def _fmt(x) -> str:
	return "n/a" if x is None else f"{x:.4g}"


def _limits_text(lower, upper) -> str:
	if lower is not None and upper is not None:
		return f"{_fmt(lower)} to {_fmt(upper)}"
	if lower is not None:
		return f"at least {_fmt(lower)}"
	if upper is not None:
		return f"at most {_fmt(upper)}"
	return "no limits"


def evaluate(criterion: dict, observation: dict) -> dict:
	"""Judge one acceptance criterion.

	`criterion`: check_type, lower_limit, upper_limit, and for the machine-data checks min_points,
	capability_index (Cpk or Ppk), min_index, rule_set.
	`observation`: {"passed": bool} for Pass/Fail; {"value": x} or {"values": [...]} for Numeric
	Range (every value must lie within the limits); {"values": [...]} for Capability and Statistical
	Control, in time order.

	Returns {"result": Pass/Fail/Pending, "observed_value", "points", "summary", "evidence"}.
	Pending means there is not enough to judge yet; nothing is ever passed by default."""
	check = criterion.get("check_type")
	if check not in CHECK_TYPES:
		raise ValueError(f"unknown check type {check!r}")
	lower, upper = _num(criterion.get("lower_limit")), _num(criterion.get("upper_limit"))
	if lower is not None and upper is not None and upper < lower:
		raise ValueError("the upper limit must not be below the lower limit")
	values = [float(v) for v in (observation.get("values") or []) if v is not None]
	out = {"result": PENDING, "observed_value": None, "points": len(values), "summary": "", "evidence": {}}

	if check == "Pass/Fail":
		passed = observation.get("passed")
		if passed is None:
			out["summary"] = "Not yet checked"
		else:
			out["result"] = PASS if passed else FAIL
			out["summary"] = "Checked and met" if passed else "Checked and not met"
		return out

	if check == "Numeric Range":
		if lower is None and upper is None:
			raise ValueError("a Numeric Range criterion needs a lower or an upper limit")
		single = _num(observation.get("value"))
		if single is not None and not values:
			values = [single]
		out["points"] = len(values)
		if not values:
			out["summary"] = "No value recorded"
			return out
		outside = [v for v in values if not _within(v, lower, upper)]
		worst = max(values, key=lambda v: _distance_outside(v, lower, upper)) if outside else None
		out["observed_value"] = values[0] if len(values) == 1 else (worst if outside else values[-1])
		out["result"] = FAIL if outside else PASS
		if len(values) == 1:
			out["summary"] = f"{_fmt(values[0])} against {_limits_text(lower, upper)}"
		else:
			out["summary"] = (
				f"{len(values) - len(outside)} of {len(values)} readings within "
				f"{_limits_text(lower, upper)} (range {_fmt(min(values))} to {_fmt(max(values))})"
			)
		out["evidence"] = {
			"lower_limit": lower,
			"upper_limit": upper,
			"minimum": min(values),
			"maximum": max(values),
			"outside": len(outside),
		}
		return out

	min_points = max(int(criterion.get("min_points") or DEFAULT_MIN_POINTS), 2)
	if len(values) < min_points:
		out["summary"] = f"{len(values)} readings; at least {min_points} are needed"
		return out

	if check == "Capability":
		if lower is None and upper is None:
			raise ValueError("a Capability criterion needs a lower or an upper specification limit")
		index = criterion.get("capability_index") or "Cpk"
		if index not in ("Cpk", "Ppk"):
			raise ValueError("capability_index must be Cpk or Ppk")
		minimum = _num(criterion.get("min_index"))
		minimum = DEFAULT_MIN_INDEX if minimum is None else minimum
		cap = spc.capability(values, lsl=lower, usl=upper)
		achieved = cap[index.lower()]
		if achieved is None:
			# no spread at all: capable only when every reading is inside the limits
			met = cap["out_of_spec"] == 0
		else:
			met = achieved >= minimum and cap["out_of_spec"] == 0
		out["result"] = PASS if met else FAIL
		out["observed_value"] = achieved
		out["summary"] = (
			f"{index} {_fmt(achieved)} (needs {_fmt(minimum)}) from {cap['n']} readings, mean "
			f"{_fmt(cap['mean'])}, specification {_limits_text(lower, upper)}, "
			f"{cap['out_of_spec']} out of specification"
		)
		out["evidence"] = {"index": index, "min_index": minimum, **cap}
		return out

	# Statistical Control: every reading judged against limits from all of them (a Phase I study)
	rules = criterion.get("rule_set") or "Nelson"
	chart = spc.imr_chart(values, rules=rules)
	signals = chart["individuals"]["signals"] + chart["moving_range"]["signals"]
	out["result"] = FAIL if signals else PASS
	out["observed_value"] = float(len(signals))
	out["summary"] = (
		f"{len(signals)} run-rule signals ({rules}) over {len(values)} readings"
		if signals
		else f"In statistical control over {len(values)} readings ({rules} rules)"
	)
	out["evidence"] = {
		"rule_set": rules,
		"centre_line": chart["individuals"]["cl"],
		"ucl": chart["individuals"]["ucl"],
		"lcl": chart["individuals"]["lcl"],
		"sigma_within": chart["sigma_within"],
		"signals": [
			{"chart": c, "index": s["index"], "rule": s["rule"], "name": s["name"]}
			for c, key in (("I", "individuals"), ("MR", "moving_range"))
			for s in chart[key]["signals"]
		][:50],
	}
	return out


def _distance_outside(v, lower, upper) -> float:
	if lower is not None and v < lower:
		return lower - v
	if upper is not None and v > upper:
		return v - upper
	return 0.0


# -------------------------------------------------------------------- executions


def execution_outcome(results: list[dict]) -> dict:
	"""The outcome of an execution from its results.

	Each result: {"criterion", "result", "critical", "deviation", "disposition"}. A result marked N/A
	is left out (the person must say why in the deviation). Returns {"outcome", "problems": [...]};
	`problems` lists what stops the execution from being approved: a pending result, a failure with
	no deviation written up, a failure with no disposition, or N/A without a reason."""
	problems = []
	outcome = PASSED
	if not results:
		return {"outcome": INCOMPLETE, "problems": ["The execution has no results"]}
	for row in results:
		label = row.get("criterion") or "a criterion"
		result = row.get("result") or PENDING
		deviation = (row.get("deviation") or "").strip()
		if result == PENDING:
			problems.append(f"{label} has no result yet")
			outcome = INCOMPLETE if outcome != FAILED else outcome
		elif result == NA:
			if row.get("critical"):
				problems.append(f"{label} is critical and cannot be marked N/A")
			elif not deviation:
				problems.append(f"{label} is marked N/A without a reason in the deviation")
		elif result == FAIL:
			if not deviation:
				problems.append(f"{label} failed and needs a deviation written up")
			if row.get("critical"):
				outcome = FAILED
			elif row.get("disposition") == ACCEPT_DEVIATION:
				if outcome == PASSED:
					outcome = PASSED_WITH_DEVIATIONS
			elif row.get("disposition") == REJECT_DEVIATION:
				outcome = FAILED
			else:
				problems.append(f"{label} failed and needs a disposition for its deviation")
				if outcome != FAILED:
					outcome = INCOMPLETE
		elif result != PASS:
			problems.append(f"{label} has an unknown result {result!r}")
	if problems and outcome != FAILED:
		outcome = INCOMPLETE
	return {"outcome": outcome, "problems": problems}


def add_months(day: date, months: int) -> date:
	"""`day` moved by whole months, clamped to the end of a shorter month."""
	month = day.month - 1 + months
	year, month = day.year + month // 12, month % 12 + 1
	return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def qualified_until(approved_on, validity_months) -> date | None:
	"""The last day a passing execution approved on `approved_on` keeps its subject qualified; None
	when the protocol sets no validity period."""
	months = int(validity_months or 0)
	if months <= 0:
		return None
	if isinstance(approved_on, datetime):
		approved_on = approved_on.date()
	return add_months(approved_on, months) - timedelta(days=1)


def qualification_status(
	executions: list[dict], today, required_runs: int = 1, due_soon_days: int = DEFAULT_DUE_SOON_DAYS
) -> dict:
	"""Where one subject (a machine or a process) stands for one protocol type.

	`executions` are the approved executions, oldest first: {"name", "protocol", "outcome",
	"approved_on", "qualified_until"}. The latest one decides: a failure means Not Qualified until a
	new execution passes. A protocol asking for several consecutive passing runs (PPQ) stays Runs
	Pending until the latest runs of that protocol all passed. A qualification with an end date is
	Due Soon within `due_soon_days` of it and Expired after it."""
	if isinstance(today, datetime):
		today = today.date()
	out = {
		"status": NOT_QUALIFIED,
		"qualified_until": None,
		"execution": None,
		"runs_passed": 0,
		"runs_required": max(int(required_runs or 1), 1),
		"days_left": None,
	}
	if not executions:
		return out
	latest = executions[-1]
	out["execution"] = latest["name"]
	if latest["outcome"] not in (PASSED, PASSED_WITH_DEVIATIONS):
		return out
	runs = 0
	for ex in reversed(executions):
		if ex["protocol"] != latest["protocol"] or ex["outcome"] not in (PASSED, PASSED_WITH_DEVIATIONS):
			break
		runs += 1
	out["runs_passed"] = runs
	if runs < out["runs_required"]:
		out["status"] = RUNS_PENDING
		return out
	until = latest.get("qualified_until")
	if isinstance(until, datetime):
		until = until.date()
	out["qualified_until"] = until
	if until is None:
		out["status"] = QUALIFIED
		return out
	out["days_left"] = (until - today).days
	if until < today:
		out["status"] = EXPIRED
	elif out["days_left"] <= due_soon_days:
		out["status"] = DUE_SOON
	else:
		out["status"] = QUALIFIED
	return out


def prerequisite_problem(code: str, prerequisite_status: dict | None) -> str | None:
	"""Why an execution of protocol type `code` may not be approved yet, or None. The prerequisite
	type (IQ before OQ before PQ before PPQ before CPV) must be current for the same subject."""
	prerequisite = protocol_type(code)["prerequisite"]
	if not prerequisite or prerequisite_status is None:
		return None
	if prerequisite_status["status"] in CURRENT:
		return None
	return (
		f"{protocol_type(prerequisite)['name']} ({prerequisite}) is {prerequisite_status['status']}; "
		f"it must be current before {protocol_type(code)['name']} ({code}) can be approved"
	)


# ---------------------------------------------------------------------- findings


def rule_key(subject_type: str, subject: str, code: str) -> str:
	return f"validation:{subject_type}:{subject}:{code}"


def findings(rows: list[dict]) -> list[dict]:
	"""Agent Suggestion dicts for qualifications that are Due Soon or Expired.

	Each row: {"subject_type": "Machine" or "Process", "subject", "protocol_type", "protocol",
	"status", "qualified_until", "days_left", "execution"}."""
	out = []
	for row in rows:
		if row["status"] not in (DUE_SOON, EXPIRED):
			continue
		code = row["protocol_type"]
		name = protocol_type(code)["name"]
		subject = f"{row['subject_type'].lower()} {row['subject']}"
		if row["status"] == EXPIRED:
			title = f"{name} of {subject} expired on {row['qualified_until']}"
			text = (
				f"The {name} ({code}) of {subject} lapsed on {row['qualified_until']}. Run protocol "
				f"{row['protocol']} again, or record why the {subject_type_noun(row)} is not in use, "
				"before relying on its output."
			)
		else:
			title = f"{name} of {subject} is due by {row['qualified_until']}"
			text = (
				f"The {name} ({code}) of {subject} lapses on {row['qualified_until']} "
				f"({row['days_left']} days). Schedule an execution of protocol {row['protocol']}."
			)
		out.append(
			{
				"rule_key": rule_key(row["subject_type"], row["subject"], code),
				"category": "Quality",
				"severity": "Critical" if row["status"] == EXPIRED else "Warning",
				"title": title,
				"suggestion": text,
				"reference_doctype": "Validation Protocol",
				"reference_name": row["protocol"],
				"evidence": {k: (str(v) if isinstance(v, date) else v) for k, v in row.items()},
			}
		)
	return out


def subject_type_noun(row) -> str:
	return "machine" if row["subject_type"] == "Machine" else "process"
