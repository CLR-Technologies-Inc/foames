# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Summaries of results.jsonl: per agent and task, and per agent overall."""

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean


def load(path: Path) -> list[dict]:
	path = path / "results.jsonl" if path.is_dir() else path
	return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
	"""95 % Wilson score interval for a success rate. With few runs it is wide, which is the point:
	two repetitions cannot separate two agents; report the interval with the rate."""
	if n == 0:
		return None
	p = successes / n
	denominator = 1 + z * z / n
	centre = (p + z * z / (2 * n)) / denominator
	half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denominator
	return round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def _summarise(rows: list[dict]) -> dict:
	successes = [r for r in rows if r["scores"]["success"]]
	costs = [r["usage"]["cost_usd"] for r in rows if r["usage"]["cost_usd"] is not None]
	first = [r for r in rows if r["rep"] == 1]
	reps_by_task = defaultdict(list)
	for r in rows:
		reps_by_task[r["task"]].append(r["scores"]["success"])
	return {
		"runs": len(rows),
		"success_rate": round(len(successes) / len(rows), 3) if rows else None,
		"success_ci95": wilson(len(successes), len(rows)),
		"first_attempt_success": round(sum(r["scores"]["success"] for r in first) / len(first), 3)
		if first
		else None,
		"reproducible_tasks": sum(1 for v in reps_by_task.values() if len(v) > 1 and all(v)),
		"quality": round(fmean(r["scores"]["quality"] for r in rows), 3) if rows else None,
		"correctness": round(fmean(r["scores"]["correctness"] for r in rows), 3) if rows else None,
		"process": round(fmean(r["scores"]["process"] for r in rows), 3) if rows else None,
		"composite": round(fmean(r["scores"]["composite"] for r in rows), 3) if rows else None,
		"mean_seconds": round(fmean(r["seconds"] for r in rows), 1) if rows else None,
		"total_cost_usd": round(sum(costs), 4) if costs else None,
		"cost_runs_known": len(costs),
		"cost_per_success_usd": round(sum(costs) / len(successes), 4)
		if costs and successes and len(costs) == len(rows)
		else None,
		"regressions": sum(
			1
			for r in rows
			if r["graded"]["regression"]["pass_rate"] is not None
			and r["graded"]["regression"]["pass_rate"] < 1.0
		),
		"purity_violations": sum(1 for r in rows if r["graded"]["purity_violations"]),
	}


def summarise(rows: list[dict]) -> dict:
	by_agent_task = defaultdict(list)
	by_agent = defaultdict(list)
	for r in rows:
		by_agent_task[(r["agent"], r["task"])].append(r)
		by_agent[r["agent"]].append(r)
	return {
		"by_agent": {
			a: {
				"model": rs[0]["model"],
				"tier": rs[0]["agent_tier"],
				"sandbox": ", ".join(sorted({r.get("sandbox", "unrecorded") for r in rs})),
				**_summarise(rs),
			}
			for a, rs in by_agent.items()
		},
		"by_agent_task": [
			{"agent": a, "task": t, **_summarise(rs)} for (a, t), rs in sorted(by_agent_task.items())
		],
	}


def _ci(s):
	ci = s.get("success_ci95")
	return f"({ci[0]:.0%} to {ci[1]:.0%})" if ci else ""


def _money(v):
	return "n/a" if v is None else f"${v:.2f}"


def markdown(summary: dict) -> str:
	lines = [
		"| Agent | Model | Tier | Sandbox | Runs | Success | First try | Quality | Composite | Mean time | Cost | Cost per success |",
		"| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
	]
	ranked = sorted(summary["by_agent"].items(), key=lambda kv: -(kv[1]["quality"] or 0))
	for agent, s in ranked:
		lines.append(
			f"| {agent} | {s['model'] or '-'} | {s['tier'] or '-'} | {s['sandbox']} | {s['runs']} | {s['success_rate']:.0%} {_ci(s)} | "
			f"{s['first_attempt_success']:.0%} | {s['quality']:.2f} | {s['composite']:.2f} | {s['mean_seconds']:.0f} s | "
			f"{_money(s['total_cost_usd'])} | {_money(s['cost_per_success_usd'])} |"
		)
	lines += [
		"",
		"| Agent | Task | Runs | Success | Quality | Correctness | Process | Mean time | Cost |",
		"| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
	]
	for s in summary["by_agent_task"]:
		lines.append(
			f"| {s['agent']} | {s['task']} | {s['runs']} | {s['success_rate']:.0%} | {s['quality']:.2f} | "
			f"{s['correctness']:.2f} | {s['process']:.2f} | {s['mean_seconds']:.0f} s | {_money(s['total_cost_usd'])} |"
		)
	if any("none" in s["sandbox"].split(", ") for s in summary["by_agent"].values()):
		lines += ["", "Runs with sandbox `none` could read the hidden tests. Do not publish them as results."]
	return "\n".join(lines) + "\n"


def write(run_dir: Path) -> dict:
	rows = load(run_dir)
	summary = summarise(rows)
	(run_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
	(run_dir / "summary.md").write_text(markdown(summary), encoding="utf-8")
	with (run_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
		fields = (
			["agent", "task", *[k for k in summary["by_agent_task"][0] if k not in ("agent", "task")]]
			if summary["by_agent_task"]
			else []
		)
		writer = csv.DictWriter(f, fieldnames=fields)
		writer.writeheader()
		writer.writerows(summary["by_agent_task"])
	return summary
