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

"""foames-bench: list, validate, run, report and recommend; `data` runs the manufacturing-data track."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from foames_bench import agents as agents_mod
from foames_bench import grading, mfgdata, recommend, report, runner, sandbox, scoring, workspace
from foames_bench import tasks as tasks_mod
from foames_bench.paths import BENCH_ROOT, repo_root

SUITE_HELP = (
	"core (the tasks outside any family), sector-case-study (one task per industrial sector) or all; "
	"ignored when --tasks names tasks"
)


def _print(*args, **kwargs):
	print(*args, **kwargs)


def cmd_list(opts):
	for t in tasks_mod.all_tasks(opts.tier, opts.suite):
		ecl = f"ECL {t.ecl}" if t.ecl else "ECL -"
		print(f"{t.id:<32} {t.tier:<7} {t.complexity:<7} TRL {','.join(t.trl_bands):<12} {ecl:<6} {t.title}")


def cmd_agents(opts):
	for a in agents_mod.load(opts.agents_file).values():
		ok, where = a.available()
		print(
			f"{a.name:<22} {a.tier or '-':<9} {a.harness or a.kind:<12} {a.model or '-':<28} {'ready' if ok else 'missing'}: {where}"
		)
	print("\nSandboxes (an agent in Docker needs its CLI in the image, not on this machine):")
	for box in (sandbox.DockerSandbox(), sandbox.UnshareSandbox(repo_root(None))):
		ok, why = box.available()
		print(f"  {box.name:<9} {'ready' if ok else 'unavailable'}: {why}")


def _out_dir(opts) -> Path:
	if opts.out:
		return Path(opts.out)
	stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
	return BENCH_ROOT / "runs" / stamp


def cmd_run(opts):
	repo = repo_root(opts.repo)
	tasks = tasks_mod.select(opts.tasks, opts.tier, opts.suite)
	available = agents_mod.load(opts.agents_file)
	names = opts.agents or ["reference"]
	missing = [n for n in names if n not in available]
	if missing:
		raise SystemExit(f"unknown agent(s): {', '.join(missing)}; see `foames-bench agents`")
	chosen = [available[n] for n in names]
	boxes = {}
	for a in chosen:
		if a.kind != "command":
			continue
		try:
			box = sandbox.make(opts.sandbox, repo, a, opts.sandbox_image, opts.sandbox_network)
		except sandbox.SandboxUnavailable as e:
			raise SystemExit(str(e)) from None
		# In a container the agent's CLI must be in the image, not on this machine.
		exe = a.command[0] if a.command else ""
		ok, where = box.has_command(exe) if isinstance(box, sandbox.DockerSandbox) else a.available()
		if not ok:
			raise SystemExit(f"agent {a.name} is not runnable here: {where}")
		boxes[a.name] = box
		print(f"{a.name}: sandbox {box.name} ({box.available()[1]})")
	out = _out_dir(opts)
	print(f"FoaMES checkout: {repo}\nResults: {out}\n")
	runner.run(
		tasks, chosen, repo, out, opts.reps, opts.keep_workspaces, opts.cap_usd, log=_print, sandboxes=boxes
	)
	summary = report.write(out)
	print("\n" + report.markdown(summary))


def cmd_report(opts):
	summary = report.write(Path(opts.run_dir))
	print(report.markdown(summary))


def cmd_validate(opts):
	"""The reference solution must succeed and doing nothing must fail, on every selected task."""
	repo = repo_root(opts.repo)
	tasks = tasks_mod.select(opts.tasks, opts.tier or "pure", opts.suite)
	builtins = agents_mod.load(opts.agents_file)
	out = _out_dir(opts)
	rows = runner.run(tasks, [builtins["reference"], builtins["noop"]], repo, out, log=_print)
	bad = []
	for r in rows:
		expected = r["agent"] == "reference"
		if r["scores"]["success"] != expected:
			bad.append(f"{r['task']}: {r['agent']} {'failed' if expected else 'succeeded'}")
	report.write(out)
	if bad:
		print("\nTask validation FAILED:\n  " + "\n  ".join(bad))
		return 1
	print(f"\nAll {len(tasks)} tasks valid: the reference passes and a no-op fails. Results in {out}")
	return 0


def cmd_prepare(opts):
	"""Make a task workspace by hand, for running an agent yourself or from Inspect AI."""
	repo = repo_root(opts.repo)
	task = tasks_mod.select([opts.task])[0]
	dest = Path(opts.dest).resolve()
	workspace.create(repo, dest, task)
	(dest.parent / f"{task.id}.prompt.md").write_text(task.prompt, encoding="utf-8")
	print(f"workspace: {dest}\nprompt:    {dest.parent / (task.id + '.prompt.md')}")


def cmd_grade(opts):
	"""Grade a workspace made by `prepare`, after an agent worked in it. Prints JSON."""
	repo = repo_root(opts.repo)
	task = tasks_mod.select([opts.task])[0]
	ws = Path(opts.workspace).resolve()
	change = workspace.collect(ws)
	box = sandbox.make(opts.sandbox, repo, image=opts.sandbox_image, network=opts.sandbox_network)
	graded = grading.grade(task, ws, repo, change, sandbox=box)
	scores = scoring.score(task, graded, opts.seconds or 0.0, opts.cost_usd)
	print(
		json.dumps(
			{"task": task.id, "scores": scores, "graded": graded}
			if opts.full
			else {"task": task.id, "scores": scores},
			indent=1,
		)
	)


def cmd_recommend(opts):
	rec = recommend.with_ecl(recommend.cell(opts.trl, opts.complexity), opts.ecl)
	tiers = recommend.load()["tiers"]
	ecl = f", ECL {rec['ecl']} ({rec['ecl_name']})" if "ecl" in rec else ""
	print(
		f"TRL {opts.trl} (band {rec['band']}), {rec['complexity']} complexity{ecl}, prior as of {rec['as_of']}"
	)
	if rec.get("human_oversight"):
		print(f"  ** {rec['human_oversight']} **")
	if rec["primary"] is None:
		print(
			"  Start with: no model tier is adequate at this ECL; agents may list options for the expert team"
		)
	else:
		print(f"  Start with: {tiers[rec['primary']]['label']}")
	if rec["alternative"]:
		print(f"  Alternative: {tiers[rec['alternative']]['label']}")
	print(f"  Human review: {rec['human_review']}")
	print(f"  Why: {rec['why']}")
	print(
		f"  Qualify a model with: {', '.join(rec['qualify_with'])} (min quality {rec['min_quality']}, every repetition must succeed)"
	)
	if rec["primary"] is not None:
		print("  Example models in that tier:")
		for ex in tiers[rec["primary"]]["examples"]:
			print("   - " + ", ".join(f"{v}" for v in ex.values()))
	if opts.results:
		ranked = recommend.qualify(report.load(Path(opts.results)), rec)
		print("\nFrom your results:")
		if not ranked:
			print("  none of the qualifying tasks were run")
		for a in ranked:
			cps = "n/a" if a["cost_per_success_usd"] is None else f"${a['cost_per_success_usd']:.2f}"
			note = (
				"QUALIFIES"
				if a["qualifies"]
				else (
					"missing " + ", ".join(a["missing_tasks"])
					if a["missing_tasks"]
					else ("tier below the ECL minimum" if a["below_ecl_tier"] else "below bar")
				)
			)
			print(
				f"  {a['agent']:<22} {a['tier'] or '-':<9} quality {a['quality']:.2f}  cost/success {cps:<8} {note}"
			)
	if opts.json:
		print(json.dumps(rec, indent=1))


def cmd_matrix(opts):
	print(recommend.matrix_markdown())


def cmd_estimate(opts):
	n = opts.agents * opts.tasks * opts.reps
	print(f"{opts.agents} agents x {opts.tasks} tasks x {opts.reps} reps = {n} runs")
	print(f"at ${opts.per_run:.2f} per run (an assumption, not a quote): ${n * opts.per_run:.2f}")
	print("Local runs of open-weight models cost electricity and time, not tokens. Use --cap-usd on `run`.")


def _sandbox_args(s, default: str):
	s.add_argument(
		"--sandbox",
		choices=["auto", "docker", "unshare", "none"],
		default=default,
		help=f"where command agents and the tests that import their code run (default: {default}); "
		"see foames_bench/sandbox.py",
	)
	s.add_argument("--sandbox-image", default=None, help=f"Docker image (default: {sandbox.DEFAULT_IMAGE})")
	s.add_argument(
		"--sandbox-network", default=None, help="Docker network (default: bridge; none for local models)"
	)


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(prog="foames-bench", description=__doc__)
	p.add_argument(
		"--agents-file", type=Path, default=None, help="agent configuration (default: benchmarks/agents.json)"
	)
	sub = p.add_subparsers(dest="command", required=True)

	s = sub.add_parser("list", help="list the tasks")
	s.add_argument("--tier", choices=["pure", "frappe", "all"], default="all")
	s.add_argument("--suite", default="all", help=SUITE_HELP)
	s.set_defaults(fn=cmd_list)

	s = sub.add_parser("agents", help="list configured agents and whether their CLI is installed")
	s.set_defaults(fn=cmd_agents)

	for name, fn, help_ in (
		("run", cmd_run, "run tasks with agents"),
		("validate", cmd_validate, "check every task with the reference and no-op agents"),
	):
		s = sub.add_parser(name, help=help_)
		s.add_argument("--tasks", nargs="*", help="task ids (default: all in the tier)")
		s.add_argument("--tier", choices=["pure", "frappe", "all"], default=None)
		s.add_argument(
			"--suite",
			default="core" if name == "run" else "all",
			help=SUITE_HELP
			+ (" (default: core, so a paid run never grows by itself)" if name == "run" else ""),
		)
		s.add_argument("--repo", help="FoaMES checkout (default: the parent of benchmarks/, or $FOAMES_REPO)")
		s.add_argument("--out", help="run directory (default: benchmarks/runs/<UTC time>)")
		if name == "run":
			s.add_argument("--agents", nargs="*", help="agent names from agents.json (default: reference)")
			s.add_argument("--reps", type=int, default=1)
			s.add_argument("--keep-workspaces", action="store_true")
			s.add_argument(
				"--cap-usd", type=float, default=None, help="stop starting runs once this much is spent"
			)
			_sandbox_args(s, "auto")
		s.set_defaults(fn=fn)

	s = sub.add_parser("report", help="summarise a run directory")
	s.add_argument("run_dir")
	s.set_defaults(fn=cmd_report)

	s = sub.add_parser("prepare", help="create one task workspace to run an agent by hand")
	s.add_argument("--task", required=True)
	s.add_argument("--dest", required=True, help="directory to create (replaced if it exists)")
	s.add_argument("--repo")
	s.set_defaults(fn=cmd_prepare)

	s = sub.add_parser("grade", help="grade a prepared workspace and print the scores as JSON")
	s.add_argument("--task", required=True)
	s.add_argument("--workspace", required=True)
	s.add_argument("--repo")
	s.add_argument("--seconds", type=float, default=None, help="wall time the agent took, for efficiency")
	s.add_argument("--cost-usd", type=float, default=None)
	s.add_argument("--full", action="store_true", help="include every test result")
	_sandbox_args(s, "none")
	s.set_defaults(fn=cmd_grade)

	s = sub.add_parser("recommend", help="model tier for a TRL and process complexity")
	s.add_argument("--trl", type=int, required=True)
	s.add_argument("--complexity", choices=recommend.COMPLEXITIES, required=True)
	s.add_argument(
		"--ecl",
		type=int,
		choices=recommend.ECLS,
		help="Equipment Complexity Level of the machine involved (1-5)",
	)
	s.add_argument("--results", help="a run directory: rank your agents for this cell")
	s.add_argument("--json", action="store_true")
	s.set_defaults(fn=cmd_recommend)

	s = sub.add_parser("matrix", help="print the TRL x complexity matrix and the ECL table")
	s.set_defaults(fn=cmd_matrix)

	mfgdata.add_parser(sub)

	s = sub.add_parser("estimate", help="pilot budget arithmetic")
	s.add_argument("--agents", type=int, default=4)
	s.add_argument("--tasks", type=int, default=6)
	s.add_argument("--reps", type=int, default=2)
	s.add_argument("--per-run", type=float, default=1.0)
	s.set_defaults(fn=cmd_estimate)
	return p


def main(argv=None) -> int:
	args = build_parser().parse_args(argv)
	return args.fn(args) or 0


if __name__ == "__main__":
	sys.exit(main())
