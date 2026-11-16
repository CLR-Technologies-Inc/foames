# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Combine benchmark run directories into one dated, published report.

  python benchmarks/scripts/publish_results.py --runs runs/ --out benchmarks/results/2026-11-16

`--runs` is searched for run directories (each with manifest.json and results.jsonl, as
`foames-bench run --out` writes them), at any depth, so one directory per job or per agent both
work. Rows of the same agent from several directories are merged. The output folder gets:

  README.md        the overview: dates, versions, ranking, reference bar, ECL reached, TRL cells
  <agent>.md       one page per agent, every run with its date
  comparison.html  the same results with a reference-bar slider that re-ranks live
  results.jsonl    every run, unchanged
  summary.json     the numbers behind the pages

Prompts, patches and transcripts stay in the workflow artifacts; they are not copied here.

Cost is what the run cost: $0 on free tiers and local models. The "list-price equivalent" prices
the same tokens at the provider's paid list price (`_list_prices` in agents.json), so free and
paid runs can be compared.

Each run directory may carry plain-text notes the workflow writes next to it: aider-version.txt,
image-id.txt, ollama-version.txt, model-digest.txt (the model's digest and pull date) and
environment.txt (where it ran). They are shown on the agent's page.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH))

from foames_bench import recommend, report
from foames_bench import tasks as tasks_mod

METRICS = ("quality", "correctness", "process", "composite")
CALIBRATION = ("reference", "noop")
TIER_ORDER = {"oss": 0, "baseline": 1, "frontier": 2}
NOTES = ("aider-version", "image-id", "ollama-version", "model-digest", "environment")


def _read(path: Path) -> str:
	return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _pct(v):
	return "n/a" if v is None else f"{v:.0%}"


def _num(v, fmt="{:.2f}"):
	return "n/a" if v is None else fmt.format(v)


def _money(v):
	if v is None:
		return "n/a"
	return f"${v:.4f}" if 0 < v < 0.01 else f"${v:.2f}"


def _ci(s):
	ci = s.get("success_ci95")
	return f"({ci[0]:.0%} to {ci[1]:.0%})" if ci else ""


def _date(iso: str) -> str:
	return iso[:10] if iso else "n/a"


def _list_price(rows, prices):
	if not prices:
		# Without list prices in agents.json, use aider's own estimate where it printed one.
		known = [
			r["usage"]["list_estimate_usd"] for r in rows if r["usage"].get("list_estimate_usd") is not None
		]
		return round(sum(known), 4) if known else None
	total = 0.0
	for r in rows:
		u = r["usage"]
		total += (
			u["input_tokens"] * prices.get("input_per_mtok", 0)
			+ u["cached_input_tokens"] * prices.get("cached_input_per_mtok", prices.get("input_per_mtok", 0))
			+ u["output_tokens"] * prices.get("output_per_mtok", 0)
		) / 1_000_000
	return round(total, 4)


def _run_notes(out: Path) -> list[str]:
	"""Notes written by hand for this day's runs (notes.md in the report folder), one bullet per line."""
	text = _read(out / "notes.md")
	return [line for line in text.splitlines() if line.startswith("- ")]


def collect(runs: Path) -> dict:
	"""Every agent's rows, merged across run directories, with the notes and manifests seen."""
	cfg = {a["name"]: a for a in json.loads((BENCH / "agents.json").read_text())["agents"]}
	agents = {}
	for src in sorted(runs.rglob("results.jsonl")):
		rd = src.parent
		try:
			manifest = json.loads(_read(rd / "manifest.json") or "{}")
		except ValueError:
			manifest = {}
		notes = {n: _read(rd / f"{n}.txt") for n in NOTES}
		for r in report.load(src):
			a = agents.setdefault(
				r["agent"],
				{
					"rows": [],
					"manifests": [],
					"notes": {n: set() for n in NOTES},
					"cfg": cfg.get(r["agent"], {"name": r["agent"]}),
				},
			)
			if a["cfg"].get("fixed_cost_usd") == 0.0 and (r["usage"].get("cost_usd") or 0) > 0:
				# A free tier costs nothing; the price aider printed is what the same tokens cost at list price.
				r["usage"]["list_estimate_usd"] = r["usage"]["cost_usd"]
				r["usage"]["cost_usd"], r["usage"]["cost_source"] = 0.0, "free tier"
			a["rows"].append(r)
			if manifest and manifest not in a["manifests"]:
				a["manifests"].append(manifest)
			for n, v in notes.items():
				if v:
					a["notes"][n].add(v)
	return agents


def reference_scores(rows):
	"""The reference solution's mean scores per task: 100 % on the comparison scale."""
	out = {}
	for t in sorted({r["task"] for r in rows if r["agent"] == "reference"}):
		rs = [r for r in rows if r["agent"] == "reference" and r["task"] == t]
		out[t] = {m: round(sum(r["scores"][m] for r in rs) / len(rs), 4) for m in METRICS}
	return out


def clears(runs, task, reference, bar, mode, metric="quality") -> bool:
	"""Every run of an agent on a task reaches the bar and keeps every invariant."""
	need = bar * reference.get(task, {}).get(metric, 1.0) if mode == "relative" else bar
	return bool(runs) and all(
		r["scores"][metric] >= need - 1e-9 and r["scores"]["invariants_kept"] for r in runs
	)


def ecl_reached(by_task: dict, task_ecl: dict, tier: str, passed) -> int | None:
	"""The highest Equipment Complexity Level n such that the agent passed every task it ran at
	ECL n or below (at least one at n), and its tier reaches the minimum tier for ECL n."""
	levels = recommend.load()["ecl"]["levels"]
	best = None
	for n in sorted({e for e in task_ecl.values() if e}):
		ran = [t for t, e in task_ecl.items() if e and e <= n and by_task.get(t)]
		at_n = [t for t in ran if task_ecl[t] == n]
		if not at_n or not all(passed(t) for t in ran):
			break
		min_tier = levels[str(n)]["min_tier"]
		if min_tier is None or TIER_ORDER.get(tier, -1) < TIER_ORDER[min_tier]:
			break
		best = n
	return best


def _cells(rows):
	rows = [r for r in rows if r["agent"] not in CALIBRATION]
	out = []
	for band in recommend.TRL_BANDS:
		for c in recommend.COMPLEXITIES:
			for a in recommend.qualify(rows, {**recommend.load()["cells"][band][c]}):
				out.append({"band": band, "complexity": c, **a})
	return out


def _use(cfg: dict) -> str:
	"""What the model was built for (agents.json "_use"); anything but coding is marked off-label."""
	use = cfg.get("_use", "")
	if not use:
		return "-"
	return use if use.startswith(("coding", "agentic coding")) else f"{use} (off-label)"


def agent_page(name, a, s, task_ecl, ecl, run_date, workflow_run):
	cfg, rows = a["cfg"], a["rows"]
	model, tier, harness = (
		rows[0].get("model") or cfg.get("model", ""),
		rows[0].get("agent_tier") or cfg.get("tier", ""),
		rows[0].get("harness") or cfg.get("harness", ""),
	)
	commits = sorted({m.get("foames_commit", "") for m in a["manifests"]} - {""})
	starts = sorted(m.get("started_at", "") for m in a["manifests"] if m.get("started_at"))
	finished = sorted(r.get("finished_at", "") for r in rows if r.get("finished_at"))
	tok = [sum(r["usage"][k] for r in rows) for k in ("input_tokens", "cached_input_tokens", "output_tokens")]
	note = lambda n: "; ".join(sorted(a["notes"][n]))  # noqa: E731
	summary_row = (
		f"| {s['runs']} | {_pct(s['success_rate'])} {_ci(s)} | {_num(s['quality'])} | {_num(s['correctness'])} | "
		f"{_num(s['process'])} | {_num(s['composite'])} | {_num(s['mean_seconds'], '{:.0f} s')} | "
		f"{tok[0]:,} / {tok[1]:,} / {tok[2]:,} | {_money(s['total_cost_usd'])} | "
		f"{_money(_list_price(rows, cfg.get('_list_prices')))} | {('ECL ' + str(ecl)) if ecl else 'none'} |"
	)
	lines = [
		f"# {name}: benchmark run of {run_date}",
		"",
		"<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->",
		"<!-- SPDX-License-Identifier: Apache-2.0 -->",
		"",
		f"- **Run dates (UTC):** started {starts[0] if starts else 'n/a'}, last run finished {finished[-1] if finished else 'n/a'}",
		f"- **Model:** `{model or '-'}` ({tier or 'calibration'} tier, built for {_use(cfg)})"
		+ (f", {note('model-digest')}" if note("model-digest") else ""),
		f"- **Harness:** {harness or 'built in'} {note('aider-version')}".rstrip(),
		f"- **Where it ran:** {note('environment') or 'GitHub-hosted runner'}; sandbox {s['sandbox']}"
		+ (f", image `{note('image-id')[:19]}`" if note("image-id") else "")
		+ (f", Ollama {note('ollama-version')}" if note("ollama-version") else ""),
		f"- **FoaMES commit:** {', '.join(f'`{c[:12]}`' for c in commits) or 'n/a'}",
		f"- {cfg.get('notes', '')}" if cfg.get("notes") else None,
		f"- Workflow run: {workflow_run}" if workflow_run else None,
		"",
		"| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |",
		"| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
		summary_row,
		"",
		"| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |",
		"| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
	]
	for r in sorted(rows, key=lambda r: (r["task"], r["rep"])):
		sc, g = r["scores"], r["graded"]
		flags = []
		if r.get("timed_out"):
			flags.append("timed out")
		if g.get("purity_violations"):
			flags.append("purity violation")
		if sc.get("tampered"):
			flags.append("tampered")
		if not sc.get("invariants_kept", True):
			flags.append("broke an invariant")
		reg = (g.get("regression") or {}).get("pass_rate")
		if reg is not None and reg < 1:
			flags.append(f"regression tests {reg:.0%}")
		lines.append(
			f"| {r['task']} (rep {r['rep']}) | {task_ecl.get(r['task']) or '-'} | {r['complexity']} | {r.get('finished_at', '')[:16]} | "
			f"{'PASS' if sc['success'] else 'fail'} | {sc['quality']:.2f} | {sc['correctness']:.2f} | {sc['process']:.2f} | "
			f"{r['seconds']:.0f} s | {r['usage']['input_tokens']:,} / {r['usage']['output_tokens']:,} | {r['exit_code']} | {', '.join(flags)} |"
		)
	return "\n".join(l for l in lines if l is not None) + "\n"


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--runs", required=True, type=Path)
	where = ap.add_mutually_exclusive_group(required=True)
	where.add_argument("--out", type=Path, help="the report folder")
	where.add_argument(
		"--out-root", type=Path, help="a results folder: the report goes in <out-root>/<run date>/"
	)
	ap.add_argument("--workflow-run", default="")
	ap.add_argument(
		"--reference",
		type=float,
		default=0.8,
		help="the comparison bar: with --reference-mode relative (default), a fraction of the reference "
		"solution's score on each task; with absolute, a score from 0 to 1. comparison.html has a slider for it.",
	)
	ap.add_argument("--reference-mode", choices=["relative", "absolute"], default="relative")
	ap.add_argument(
		"--raw-only",
		action="store_true",
		help="only add the run files under <out>/runs/ (no README, pages or comparison), so a workflow run "
		"that overlaps another can commit without touching the files the other one rewrites",
	)
	opts = ap.parse_args(argv)

	agents = collect(opts.runs)
	all_rows = [r for a in agents.values() for r in a["rows"]]
	if not all_rows:
		raise SystemExit(f"no results.jsonl under {opts.runs}")
	starts = sorted(
		m.get("started_at", "") for a in agents.values() for m in a["manifests"] if m.get("started_at")
	)
	run_date = _date(starts[0] if starts else "")
	if opts.out is None:
		opts.out = opts.out_root / run_date
	opts.out.mkdir(parents=True, exist_ok=True)
	# Keep each run directory's small files (results, manifest, notes) under <out>/runs/<name>, so a
	# later workflow run of the same day adds to this report instead of replacing it. A directory of
	# the same name (the same agent and task) is replaced by the newer one.
	kept = opts.out / "runs"
	for src in sorted(opts.runs.rglob("results.jsonl")):
		if kept in src.parents or (opts.raw_only and src.parent.name == "calibration"):
			continue
		dest = kept / src.parent.name
		shutil.rmtree(dest, ignore_errors=True)
		dest.mkdir(parents=True)
		for f in [src, *src.parent.glob("manifest.json"), *src.parent.glob("*.txt")]:
			shutil.copy2(f, dest / f.name)
	if opts.raw_only:
		print(f"added run files under {kept}; run again without --raw-only to rebuild the report")
		return
	agents = collect(kept)
	all_rows = [r for a in agents.values() for r in a["rows"]]
	starts = sorted(
		m.get("started_at", "") for a in agents.values() for m in a["manifests"] if m.get("started_at")
	)
	summary = report.summarise(all_rows)
	reference = reference_scores(all_rows)
	task_ids = sorted({r["task"] for r in all_rows})
	task_ecl = {t.id: t.ecl for t in tasks_mod.all_tasks()}
	finishes = sorted(r.get("finished_at", "") for r in all_rows if r.get("finished_at"))
	published = datetime.now(timezone.utc).isoformat(timespec="seconds")

	overview = []
	for name, a in agents.items():
		s = summary["by_agent"][name]
		by_task = {}
		for r in a["rows"]:
			by_task.setdefault(r["task"], []).append(r)
		passed = lambda t, bt=by_task: all(r["scores"]["success"] for r in bt.get(t, []))  # noqa: E731
		ecl = (
			None
			if name in CALIBRATION
			else ecl_reached(by_task, task_ecl, a["rows"][0].get("agent_tier") or "", passed)
		)
		(opts.out / f"{name}.md").write_text(
			agent_page(name, a, s, task_ecl, ecl, run_date, opts.workflow_run), encoding="utf-8"
		)
		overview.append(
			{
				"agent": name,
				"s": s,
				"cfg": a["cfg"],
				"by_task": by_task,
				"ecl": ecl,
				"tokens": (
					sum(r["usage"]["input_tokens"] for r in a["rows"]),
					sum(r["usage"]["output_tokens"] for r in a["rows"]),
				),
				"list_price": _list_price(a["rows"], a["cfg"].get("_list_prices")),
				"cleared": sum(
					clears(by_task.get(t, []), t, reference, opts.reference, opts.reference_mode)
					for t in task_ids
				),
				"digest": "; ".join(sorted(a["notes"]["model-digest"])),
				"env": "; ".join(sorted(a["notes"]["environment"])),
			}
		)
	ranked = sorted(
		(o for o in overview if o["agent"] not in CALIBRATION),
		key=lambda o: (-o["cleared"], -(o["s"]["quality"] or 0)),
	)
	calibration = [o for o in overview if o["agent"] in CALIBRATION]

	with (opts.out / "results.jsonl").open("w", encoding="utf-8") as f:
		for r in all_rows:
			f.write(json.dumps(r) + "\n")
	cells = _cells(all_rows)
	(opts.out / "summary.json").write_text(
		json.dumps(
			{
				"run_date": run_date,
				"started_at": starts[0] if starts else None,
				"finished_at": finishes[-1] if finishes else None,
				"published_at": published,
				"reference_bar": {"value": opts.reference, "mode": opts.reference_mode},
				"reference_scores": reference,
				"ecl_reached": {o["agent"]: o["ecl"] for o in ranked},
				"summary": summary,
				"qualification": cells,
			},
			indent=1,
		),
		encoding="utf-8",
	)

	commits = sorted(
		{m.get("foames_commit", "")[:10] for a in agents.values() for m in a["manifests"]} - {""}
	)
	bar_text = (
		f"{opts.reference:.0%} of the reference solution's quality on each task"
		if opts.reference_mode == "relative"
		else f"quality of at least {opts.reference:.2f}"
	)
	dates_line = (
		f"**Run of {run_date}.** Runs started {starts[0] if starts else 'n/a'} and the last finished "
		f"{finishes[-1] if finishes else 'n/a'} (UTC), on FoaMES commit {', '.join(f'`{c}`' for c in commits) or 'n/a'}. "
		f"Report built {published}." + (f" Workflow run: {opts.workflow_run}." if opts.workflow_run else "")
	)
	intro = (
		"Every agent is aider driving one model on the benchmark's pure tasks, in the benchmark's sandbox. Local "
		"models ran on Ollama; hosted models, where present, on their providers' free API tiers. Each model's "
		"page gives its exact version (digest or API model id), where it ran and when. Ranking is by tasks cleared "
		"at the reference bar, then quality (correctness and process, without cost), as in "
		"[docs/methodology.md](../../docs/methodology.md). One repetition cannot separate close agents: read the intervals."
	)
	bar_note = (
		f'**Reference bar: {bar_text}**, and every invariant kept. "Clears" counts the tasks where every '
		"repetition reached it. Move the bar with the slider in [comparison.html](comparison.html) (open it in a "
		"browser), or rebuild with `--reference`."
	)
	ecl_note = (
		"- **ECL reached** is the highest Equipment Complexity Level at which the agent passed every task it ran at "
		"that level and below, and whose minimum model tier its tier meets (data/recommendations.json). No task above "
		"ECL 3 exists yet, so ECL 4 and 5 cannot be reached; at those levels the matrix calls for a human expert anyway."
	)
	cost_note = (
		"- Cost is what the runs cost: $0 on free API tiers and for local models (electricity and runner time are not "
		"counted). The list-price equivalent prices the same tokens at the provider's paid list price (from "
		"agents.json, or else the estimate aider printed during the run)."
	)
	token_note = (
		"- Aider prints token counts rounded to the nearest hundred above 1,000, so token totals are approximate. "
		"Local models report no cost, so their token counts may also read zero."
	)
	use_note = (
		'- "Built for" is what the model\'s makers tuned it for. Models marked off-label (general chat, reasoning, tiny '
		"or domain models) are not meant for agentic coding; they are here to show how far each kind gets on FoaMES work."
	)
	cpu_note = (
		"- Local models on GitHub-hosted runners ran on CPU (4 vCPU, 16 GB). Speed is not scored against them here "
		"beyond the efficiency term in the composite; read quality."
	)
	lines = [
		f"# FoaMES agent benchmark results: run of {run_date}",
		"",
		"<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->",
		"<!-- SPDX-License-Identifier: Apache-2.0 -->",
		"",
		dates_line,
		"",
		intro,
		"",
		bar_note,
		"",
		"| Agent | Model | Built for | Tier | Ran on | Runs | Clears bar | Success (95 % CI) | Quality | Composite | Mean time | Tokens in / out | Cost | List-price equivalent | ECL reached |",
		"| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
	]
	for o in ranked + calibration:
		s = o["s"]
		lines.append(
			f"| [{o['agent']}]({o['agent']}.md) | `{s['model'] or '-'}` | {_use(o['cfg'])} | {s['tier'] or 'calibration'} | {o['env'] or 'runner'} | "
			f"{s['runs']} | {o['cleared']} / {len(task_ids)} | {_pct(s['success_rate'])} {_ci(s)} | {_num(s['quality'])} | "
			f"{_num(s['composite'])} | {_num(s['mean_seconds'], '{:.0f} s')} | {o['tokens'][0]:,} / {o['tokens'][1]:,} | "
			f"{_money(s['total_cost_usd'])} | {_money(o['list_price'])} | "
			f"{'n/a' if o['agent'] in CALIBRATION else ('ECL ' + str(o['ecl']) if o['ecl'] else 'none')} |"
		)
	lines += [
		"",
		"## Quality by task",
		"",
		"| Agent | " + " | ".join(f"{t} (ECL {task_ecl.get(t) or '-'})" for t in task_ids) + " |",
		"| --- |" + " ---: |" * len(task_ids),
	]
	for o in ranked + calibration:
		row = []
		for t in task_ids:
			rs = o["by_task"].get(t, [])
			if not rs:
				row.append("")
				continue
			q = sum(r["scores"]["quality"] for r in rs) / len(rs)
			ok = all(r["scores"]["success"] for r in rs)
			row.append(f"{q:.2f} {'PASS' if ok else 'fail'}")
		lines.append(f"| {o['agent']} | " + " | ".join(row) + " |")

	qualified = [c for c in cells if c["qualifies"]]
	lines += ["", "## Which TRL x complexity cells each agent qualifies for", ""]
	if qualified:
		lines += ["| TRL band | Complexity | Qualified agents (cheapest first) |", "| --- | --- | --- |"]
		for band in recommend.TRL_BANDS:
			for c in recommend.COMPLEXITIES:
				names = [q["agent"] for q in qualified if q["band"] == band and q["complexity"] == c]
				lines.append(f"| {band} | {c} | {', '.join(names) if names else 'none yet'} |")
	else:
		lines.append(
			"No agent qualified for any cell yet: a cell needs every repetition of its qualifying tasks to succeed "
			"with mean quality at or above the cell's minimum (data/recommendations.json)."
		)
	lines += [
		"",
		"## Notes",
		"",
		ecl_note,
		cost_note,
		token_note,
		*[
			f"- Not run: `{a['name']}`: {a['_skip_reason']}."
			for a in json.loads((BENCH / "agents.json").read_text())["agents"]
			if a.get("_skip_reason")
		],
		cpu_note,
		use_note,
		*_run_notes(opts.out),
		"",
	]
	(opts.out / "README.md").write_text("\n".join(lines), encoding="utf-8")

	entries = [
		{
			"agent": o["agent"],
			"model": o["s"]["model"] or "",
			"tier": o["s"]["tier"] or "calibration",
			"env": o["env"] or "runner",
			"digest": o["digest"],
			"tokens_in": o["tokens"][0],
			"tokens_out": o["tokens"][1],
			"cost": _money(o["s"]["total_cost_usd"]),
			"list_price": _money(o["list_price"]),
			"tasks": {
				t: [
					{
						**{m: r["scores"][m] for m in METRICS},
						"invariants_ok": r["scores"]["invariants_kept"],
						"success": r["scores"]["success"],
					}
					for r in o["by_task"].get(t, [])
				]
				for t in task_ids
			},
		}
		for o in ranked + [c for c in calibration if c["agent"] == "noop"]
	]
	levels = recommend.load()["ecl"]["levels"]
	data = {
		"title": f"FoaMES agent benchmark: run of {run_date}",
		"meta": dates_line.replace("**", "").replace("`", ""),
		"footer": "Bar applies per task: in relative mode the reference solution's own score on that task is 100 %. "
		"Ranked by tasks cleared, then mean score. ECL reached follows the bar you set. Data: results.jsonl in this folder; "
		"scoring: benchmarks/docs/methodology.md.",
		"default_bar": opts.reference,
		"default_mode": opts.reference_mode,
		"tasks": task_ids,
		"task_ecl": task_ecl,
		"ecl_min_tier": {k: v["min_tier"] for k, v in levels.items()},
		"reference": reference,
		"agents": entries,
	}
	template = (Path(__file__).parent / "comparison_template.html").read_text(encoding="utf-8")
	blob = json.dumps(data).replace("</", "<\\/")
	(opts.out / "comparison.html").write_text(template.replace("__DATA__", blob), encoding="utf-8")
	print(f"wrote {opts.out} ({len(all_rows)} runs, {len(ranked)} agents, run of {run_date})")


if __name__ == "__main__":
	main()
