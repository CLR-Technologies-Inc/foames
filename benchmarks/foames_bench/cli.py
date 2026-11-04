# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""foames-bench: list, validate, run, report and recommend."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from foames_bench import agents as agents_mod
from foames_bench import grading, recommend, report, runner, scoring, workspace
from foames_bench import tasks as tasks_mod
from foames_bench.paths import BENCH_ROOT, repo_root


def _print(*args, **kwargs):
	print(*args, **kwargs)


def cmd_list(args):
	for t in tasks_mod.all_tasks(args.tier):
		print(f"{t.id:<26} {t.tier:<7} {t.complexity:<7} TRL {','.join(t.trl_bands):<12} {t.title}")


def cmd_agents(args):
	for a in agents_mod.load(args.agents_file).values():
		ok, where = a.available()
		print(
			f"{a.name:<22} {a.tier or '-':<9} {a.harness or a.kind:<12} {a.model or '-':<28} {'ready' if ok else 'missing'}: {where}"
		)


def _out_dir(args) -> Path:
	if args.out:
		return Path(args.out)
	stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
	return BENCH_ROOT / "runs" / stamp


def cmd_run(args):
	repo = repo_root(args.repo)
	tasks = tasks_mod.select(args.tasks, args.tier)
	available = agents_mod.load(args.agents_file)
	names = args.agents or ["reference"]
	missing = [n for n in names if n not in available]
	if missing:
		raise SystemExit(f"unknown agent(s): {', '.join(missing)}; see `foames-bench agents`")
	chosen = [available[n] for n in names]
	for a in chosen:
		ok, where = a.available()
		if not ok:
			raise SystemExit(f"agent {a.name} is not runnable here: {where}")
	out = _out_dir(args)
	print(f"FoaMES checkout: {repo}\nResults: {out}\n")
	runner.run(tasks, chosen, repo, out, args.reps, args.keep_workspaces, args.cap_usd, log=_print)
	summary = report.write(out)
	print("\n" + report.markdown(summary))


def cmd_report(args):
	summary = report.write(Path(args.run_dir))
	print(report.markdown(summary))


def cmd_validate(args):
	"""The reference solution must succeed and doing nothing must fail, on every selected task."""
	repo = repo_root(args.repo)
	tasks = tasks_mod.select(args.tasks, args.tier or "pure")
	builtins = agents_mod.load(args.agents_file)
	out = _out_dir(args)
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


def cmd_prepare(args):
	"""Make a task workspace by hand, for running an agent yourself or from Inspect AI."""
	repo = repo_root(args.repo)
	task = tasks_mod.select([args.task])[0]
	dest = Path(args.dest).resolve()
	workspace.create(repo, dest, task)
	(dest.parent / f"{task.id}.prompt.md").write_text(task.prompt, encoding="utf-8")
	print(f"workspace: {dest}\nprompt:    {dest.parent / (task.id + '.prompt.md')}")


def cmd_grade(args):
	"""Grade a workspace made by `prepare`, after an agent worked in it. Prints JSON."""
	repo = repo_root(args.repo)
	task = tasks_mod.select([args.task])[0]
	ws = Path(args.workspace).resolve()
	change = workspace.collect(ws)
	graded = grading.grade(task, ws, repo, change)
	scores = scoring.score(task, graded, args.seconds or 0.0, args.cost_usd)
	print(
		json.dumps(
			{"task": task.id, "scores": scores, "graded": graded}
			if args.full
			else {"task": task.id, "scores": scores},
			indent=1,
		)
	)


def cmd_recommend(args):
	rec = recommend.cell(args.trl, args.complexity)
	tiers = recommend.load()["tiers"]
	print(f"TRL {args.trl} (band {rec['band']}), {rec['complexity']} complexity, prior as of {rec['as_of']}")
	print(f"  Start with: {tiers[rec['primary']]['label']}")
	if rec["alternative"]:
		print(f"  Alternative: {tiers[rec['alternative']]['label']}")
	print(f"  Human review: {rec['human_review']}")
	print(f"  Why: {rec['why']}")
	print(
		f"  Qualify a model with: {', '.join(rec['qualify_with'])} (min quality {rec['min_quality']}, every repetition must succeed)"
	)
	print("  Example models in that tier:")
	for ex in tiers[rec["primary"]]["examples"]:
		print("   - " + ", ".join(f"{v}" for v in ex.values()))
	if args.results:
		ranked = recommend.qualify(report.load(Path(args.results)), rec)
		print("\nFrom your results:")
		if not ranked:
			print("  none of the qualifying tasks were run")
		for a in ranked:
			cps = "n/a" if a["cost_per_success_usd"] is None else f"${a['cost_per_success_usd']:.2f}"
			note = (
				"QUALIFIES"
				if a["qualifies"]
				else ("missing " + ", ".join(a["missing_tasks"]) if a["missing_tasks"] else "below bar")
			)
			print(
				f"  {a['agent']:<22} {a['tier'] or '-':<9} quality {a['quality']:.2f}  cost/success {cps:<8} {note}"
			)
	if args.json:
		print(json.dumps(rec, indent=1))


def cmd_matrix(args):
	print(recommend.matrix_markdown())


def cmd_estimate(args):
	n = args.agents * args.tasks * args.reps
	print(f"{args.agents} agents x {args.tasks} tasks x {args.reps} reps = {n} runs")
	print(f"at ${args.per_run:.2f} per run (an assumption, not a quote): ${n * args.per_run:.2f}")
	print("Local runs of open-weight models cost electricity and time, not tokens. Use --cap-usd on `run`.")


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(prog="foames-bench", description=__doc__)
	p.add_argument(
		"--agents-file", type=Path, default=None, help="agent configuration (default: benchmarks/agents.json)"
	)
	sub = p.add_subparsers(dest="command", required=True)

	s = sub.add_parser("list", help="list the tasks")
	s.add_argument("--tier", choices=["pure", "frappe", "all"], default="all")
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
		s.add_argument("--repo", help="FoaMES checkout (default: the parent of benchmarks/, or $FOAMES_REPO)")
		s.add_argument("--out", help="run directory (default: benchmarks/runs/<UTC time>)")
		if name == "run":
			s.add_argument("--agents", nargs="*", help="agent names from agents.json (default: reference)")
			s.add_argument("--reps", type=int, default=1)
			s.add_argument("--keep-workspaces", action="store_true")
			s.add_argument(
				"--cap-usd", type=float, default=None, help="stop starting runs once this much is spent"
			)
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
	s.set_defaults(fn=cmd_grade)

	s = sub.add_parser("recommend", help="model tier for a TRL and process complexity")
	s.add_argument("--trl", type=int, required=True)
	s.add_argument("--complexity", choices=recommend.COMPLEXITIES, required=True)
	s.add_argument("--results", help="a run directory: rank your agents for this cell")
	s.add_argument("--json", action="store_true")
	s.set_defaults(fn=cmd_recommend)

	s = sub.add_parser("matrix", help="print the TRL x complexity matrix")
	s.set_defaults(fn=cmd_matrix)

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
