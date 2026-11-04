# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Run tasks x agents x repetitions and write one result per run.

Layout of a run directory:

  runs/<run id>/
    manifest.json                 the FoaMES commit, the bench version, the agents and tasks
    results.jsonl                 one line per run (the report reads only this)
    <task>/<agent>/rep-<n>/
      prompt.md  agent.stdout  agent.stderr  change.patch  result.json
      workspace/                  kept only with --keep-workspaces
"""

import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from foames_bench import __version__, grading, scoring, usage, workspace
from foames_bench import agents as agents_mod


def _foames_commit(repo: Path) -> str:
	result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
	return result.stdout.strip() if result.returncode == 0 else "unknown"


def run_one(task, agent, repo: Path, run_dir: Path, keep_workspace: bool = False) -> dict:
	run_dir.mkdir(parents=True, exist_ok=True)
	ws = workspace.create(repo, run_dir / "workspace", task)
	result = agents_mod.run(agent, task, ws, run_dir)
	change = workspace.collect(ws)
	(run_dir / "change.patch").write_text(change["patch"], encoding="utf-8")
	graded = grading.grade(task, ws, repo, change)
	used = usage.parse(agent.usage_parser, result.stdout, agent.prices)
	if used.cost_usd is None and agent.fixed_cost_usd is not None:
		used.cost_usd, used.cost_source = agent.fixed_cost_usd, "local"
	scores = scoring.score(task, graded, result.seconds, used.cost_usd)
	row = {
		"task": task.id,
		"tier": task.tier,
		"complexity": task.complexity,
		"agent": agent.name,
		"agent_tier": agent.tier,
		"harness": agent.harness,
		"model": agent.model,
		"rep": int(run_dir.name.split("-")[-1]) if run_dir.name.startswith("rep-") else 1,
		"exit_code": result.exit_code,
		"timed_out": result.timed_out,
		"seconds": round(result.seconds, 2),
		"usage": used.to_dict(),
		"scores": scores,
		"graded": graded,
		"finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
	}
	(run_dir / "result.json").write_text(json.dumps(row, indent=1), encoding="utf-8")
	if not keep_workspace:
		shutil.rmtree(ws, ignore_errors=True)
	return row


def run(
	tasks,
	agent_list,
	repo: Path,
	out: Path,
	reps: int = 1,
	keep_workspaces: bool = False,
	cap_usd=None,
	log=print,
):
	"""Every task with every agent, `reps` times. With `cap_usd`, stop starting runs once the
	reported and estimated spend reaches the cap (a run already started is not cut short)."""
	out.mkdir(parents=True, exist_ok=True)
	manifest = {
		"bench_version": __version__,
		"foames_commit": _foames_commit(repo),
		"python": platform.python_version(),
		"platform": platform.platform(),
		"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
		"reps": reps,
		"tasks": [t.id for t in tasks],
		"agents": [
			{"name": a.name, "model": a.model, "tier": a.tier, "harness": a.harness} for a in agent_list
		],
	}
	(out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
	rows = []
	spent = 0.0
	with (out / "results.jsonl").open("a", encoding="utf-8") as sink:
		for task in tasks:
			for agent in agent_list:
				for rep in range(1, reps + 1):
					if cap_usd is not None and spent >= cap_usd:
						log(f"spending cap of ${cap_usd:.2f} reached (${spent:.2f}); stopping")
						return rows
					run_dir = out / task.id / agent.name / f"rep-{rep}"
					log(f"{task.id:<24} {agent.name:<20} rep {rep} ...", end=" ", flush=True)
					row = run_one(task, agent, repo, run_dir, keep_workspaces)
					s = row["scores"]
					cost = row["usage"]["cost_usd"]
					log(
						f"{'PASS' if s['success'] else 'fail'}  quality {s['quality']:.2f}  composite {s['composite']:.2f}"
						f"  {row['seconds']:.0f} s  {f'${cost:.2f}' if cost is not None else 'cost n/a'}"
					)
					sink.write(json.dumps(row) + "\n")
					sink.flush()
					rows.append(row)
					spent += cost or 0.0
	return rows
