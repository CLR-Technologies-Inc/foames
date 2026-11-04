# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""From a graded run to three scores and a composite.

  Engineering correctness   40 %   hidden functional tests, the repository's own tests
  Process-development       35 %   manufacturing invariants, tests the agent wrote, scope, notes
  Delivery efficiency       25 %   cost and time against the task's budget

A run succeeds when correctness reaches the task's gate (0.8 by default) and every invariant test
passes. Efficiency is only paid on success, so a cheap wrong answer never outranks a correct one. `quality` is correctness and process alone, rescaled to
0..1, and is what the recommendation tables rank on; cost is reported next to it, not mixed in.
"""

WEIGHTS = {"correctness": 0.40, "process": 0.35, "efficiency": 0.25}


def _rate(value, default=0.0):
	return default if value is None else value


def score(task, graded: dict, seconds: float, cost_usd: float | None) -> dict:
	functional = graded["hidden"].get("functional", {}).get("pass_rate")
	invariant = graded["hidden"].get("invariant", {}).get("pass_rate")
	regression = graded["regression"]["pass_rate"]
	rubric = graded.get("rubric")
	missing = [d for d, ok in graded["deliverables"].items() if not ok]

	# Correctness: the hidden functional tests carry it; the repository's own tests guard
	# against regressions. A document task's executable acceptance criteria count here too.
	parts = [(0.75, functional), (0.25, regression)]
	if rubric is not None and functional is None:
		parts = [(0.75, _rate(graded["agent_tests"]["pass_rate"])), (0.25, regression)]
	known = [(w, v) for w, v in parts if v is not None]
	correctness = sum(w * v for w, v in known) / sum(w for w, _ in known) if known else 0.0
	if missing:
		correctness *= 0.5

	# Process: did the change keep the plant's rules, did the agent verify its own work, did it
	# stay inside the task, and did it say what it assumed.
	agent_tests = graded["agent_tests"]
	# Credit needs new test functions in a discovered test file and at least one of them executed:
	# skipped-only or undiscovered tests earn nothing.
	executed = [t for t in agent_tests.get("tests", []) if t["outcome"] != "skip"]
	wrote_tests = (
		1.0 if agent_tests["new_test_functions"] > 0 and executed and agent_tests["pass_rate"] == 1.0 else 0.0
	)
	in_scope = (
		0.0
		if not graded["changed_files"]
		else 1.0
		if not graded["out_of_scope"]
		else max(0.0, 1.0 - 0.25 * len(graded["out_of_scope"]))
	)
	notes = min(graded["notes_words"] / 80.0, 1.0)
	if rubric is not None:
		process = (
			0.45 * rubric["score"]
			+ 0.25 * _rate(invariant)
			+ 0.1 * wrote_tests
			+ 0.1 * in_scope
			+ 0.1 * notes
		)
	else:
		process = 0.5 * _rate(invariant) + 0.2 * wrote_tests + 0.15 * in_scope + 0.15 * notes
	if graded["purity_violations"]:
		process *= 0.5

	# A run succeeds when it is correct enough and keeps every manufacturing invariant: AGENTS.md
	# says a change that breaks one is not merged, so neither is it counted as a success here.
	invariants_kept = invariant is None or invariant == 1.0
	success = correctness >= task.correctness_gate and invariants_kept and not graded["purity_violations"]

	# Efficiency, gated on success.
	efficiency = 0.0
	if success:
		time_part = 1.0 - min(seconds / task.budget_seconds, 1.0) if task.budget_seconds else 0.0
		if cost_usd is None:
			efficiency = time_part
		else:
			cost_part = 1.0 - min(cost_usd / task.budget_usd, 1.0) if task.budget_usd else 0.0
			efficiency = 0.5 * cost_part + 0.5 * time_part

	composite = (
		WEIGHTS["correctness"] * correctness
		+ WEIGHTS["process"] * process
		+ WEIGHTS["efficiency"] * efficiency
	)
	quality = (WEIGHTS["correctness"] * correctness + WEIGHTS["process"] * process) / (
		WEIGHTS["correctness"] + WEIGHTS["process"]
	)
	return {
		"correctness": round(correctness, 4),
		"process": round(process, 4),
		"efficiency": round(efficiency, 4),
		"quality": round(quality, 4),
		"composite": round(composite, 4),
		"invariants_kept": invariants_kept,
		"success": success,
	}
