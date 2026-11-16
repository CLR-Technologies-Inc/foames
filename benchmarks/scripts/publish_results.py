# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 CLR Technologies Inc.

"""Combine benchmark run directories into one published report.

  python benchmarks/scripts/publish_results.py --runs runs/ --out benchmarks/results/2026-11-16

`--runs` holds one run directory per agent (each with manifest.json and results.jsonl, as
`foames-bench run --out` writes them). The output folder gets README.md (the overview), one
<agent>.md per agent, results.jsonl (every run, unchanged) and summary.json. Prompts, patches and
transcripts stay in the workflow artifacts; they are not copied into the repository.

Cost is what the run cost: $0 on free tiers and local models. For free hosted models, the
"list-price equivalent" prices the same tokens at the provider's paid list price from the agent's
`_list_prices` in agents.json, so free and paid runs can be compared.
"""

import argparse
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH))

from foames_bench import recommend, report  # noqa: E402

ECL_NOTE = (
	"No ECL (engineering confidence level) tier is on main yet; this column fills in once the ECL "
	"tasks land."
)


def _read(path: Path, default=""):
	return path.read_text(encoding="utf-8").strip() if path.exists() else default


def _list_price(rows, prices):
	if not prices:
		return None
	total = 0.0
	for r in rows:
		u = r["usage"]
		total += (
			u["input_tokens"] * prices.get("input_per_mtok", 0)
			+ u["cached_input_tokens"] * prices.get("cached_input_per_mtok", prices.get("input_per_mtok", 0))
			+ u["output_tokens"] * prices.get("output_per_mtok", 0)
		) / 1_000_000
	return round(total, 4)


def _pct(v):
	return "n/a" if v is None else f"{v:.0%}"


def _num(v, fmt="{:.2f}"):
	return "n/a" if v is None else fmt.format(v)


def _money(v):
	return "n/a" if v is None else f"${v:.4f}" if v < 0.01 and v > 0 else f"${v:.2f}"


def _cells(rows):
	# The built-in reference and no-op agents calibrate the grader; they are not candidates.
	rows = [r for r in rows if r["agent"] not in ("reference", "noop")]
	out = []
	for band in recommend.TRL_BANDS:
		for c in recommend.COMPLEXITIES:
			rec = {**recommend.load()["cells"][band][c]}
			for a in recommend.qualify(rows, rec):
				out.append({"band": band, "complexity": c, **a})
	return out


def collect(runs: Path):
	agents_cfg = {a["name"]: a for a in json.loads((BENCH / "agents.json").read_text())["agents"]}
	blocks = []
	for d in sorted(p for p in runs.iterdir() if p.is_dir()):
		src = d / "results.jsonl"
		if not src.exists():
			# download-artifact puts each artifact in its own folder; a run may be one level down.
			found = list(d.glob("*/results.jsonl"))
			if not found:
				blocks.append({"dir": d.name, "rows": [], "manifest": {}, "missing": True})
				continue
			src = found[0]
		rd = src.parent
		manifest = json.loads(_read(rd / "manifest.json", "{}") or "{}")
		by_agent = {}
		for r in report.load(src):
			by_agent.setdefault(r["agent"], []).append(r)
		for name, rows in by_agent.items():
			blocks.append(
				{
					"dir": d.name,
					"run_dir": rd,
					"rows": rows,
					"manifest": manifest,
					"aider": _read(rd / "aider-version.txt") if rows[0].get("harness") == "aider" else "",
					"image": _read(rd / "image-id.txt") if rows[0].get("sandbox") == "docker" else "",
					"ollama": _read(rd / "ollama-version.txt"),
					"cfg": agents_cfg.get(name, {"name": name}),
				}
			)
	return blocks


def agent_page(b, s, tasks_summary, workflow_run):
	cfg, rows, m = b["cfg"], b["rows"], b["manifest"]
	tok_in = sum(r["usage"]["input_tokens"] for r in rows)
	tok_cached = sum(r["usage"]["cached_input_tokens"] for r in rows)
	tok_out = sum(r["usage"]["output_tokens"] for r in rows)
	lp = _list_price(rows, cfg.get("_list_prices"))
	lines = [
		f"# {cfg.get('name', b['dir'])}",
		"",
		"<!-- SPDX-License-Identifier: Apache-2.0 -->",
		"",
		f"- Model: `{cfg.get('model', '')}` ({cfg.get('tier', '')} tier), harness: {cfg.get('harness', '')} {b['aider']}",
		f"- {cfg.get('notes', '')}",
		f"- FoaMES commit: `{m.get('foames_commit', 'unknown')}`, bench {m.get('bench_version', '')}, started {m.get('started_at', '')}",
		f"- Sandbox: {s['sandbox']}, image `{b['image'][:19]}`" + (f", Ollama {b['ollama']}" if b["ollama"] else ""),
		f"- Workflow run: {workflow_run}" if workflow_run else "",
		"",
		"| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL tier |",
		"| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
		f"| {s['runs']} | {_pct(s['success_rate'])} {_ci(s)} | {_num(s['quality'])} | {_num(s['correctness'])} | {_num(s['process'])} | "
		f"{_num(s['composite'])} | {_num(s['mean_seconds'], '{:.0f} s')} | {tok_in:,} / {tok_cached:,} / {tok_out:,} | "
		f"{_money(s['total_cost_usd'])} | {_money(lp)} | n/a |",
		"",
		"| Task | Complexity | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |",
		"| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
	]
	for r in rows:
		sc, g = r["scores"], r["graded"]
		notes = []
		if r["timed_out"]:
			notes.append("timed out")
		if g.get("purity_violations"):
			notes.append("purity violation")
		if sc.get("tampered"):
			notes.append("tampered")
		reg = (g.get("regression") or {}).get("pass_rate")
		if reg is not None and reg < 1:
			notes.append(f"regression tests {reg:.0%}")
		lines.append(
			f"| {r['task']} (rep {r['rep']}) | {r['complexity']} | {'PASS' if sc['success'] else 'fail'} | {sc['quality']:.2f} | "
			f"{sc['correctness']:.2f} | {sc['process']:.2f} | {r['seconds']:.0f} s | "
			f"{r['usage']['input_tokens']:,} / {r['usage']['output_tokens']:,} | {r['exit_code']} | {', '.join(notes)} |"
		)
	return "\n".join(l for l in lines if l is not None) + "\n"


def _ci(s):
	ci = s.get("success_ci95")
	return f"({ci[0]:.0%} to {ci[1]:.0%})" if ci else ""


METRICS = ("quality", "correctness", "process", "composite")


def reference_scores(rows):
	"""The reference solution's mean scores per task: the top of the comparison scale."""
	out = {}
	for t in sorted({r["task"] for r in rows if r["agent"] == "reference"}):
		rs = [r for r in rows if r["agent"] == "reference" and r["task"] == t]
		out[t] = {m: round(sum(r["scores"][m] for r in rs) / len(rs), 4) for m in METRICS}
	return out


def clears(runs, task, reference, bar, mode, metric="quality"):
	"""Whether every run of an agent on a task reaches the bar and keeps every invariant."""
	need = bar * reference.get(task, {}).get(metric, 1.0) if mode == "relative" else bar
	return bool(runs) and all(r["scores"][metric] >= need - 1e-9 and r["scores"]["invariants_kept"] for r in runs)


def write_html(out: Path, entries, reference, tasks, bar, mode, meta, footer):
	data = {
		"meta": meta,
		"footer": footer,
		"default_bar": bar,
		"default_mode": mode,
		"tasks": tasks,
		"reference": reference,
		"agents": entries,
	}
	template = (Path(__file__).parent / "comparison_template.html").read_text(encoding="utf-8")
	blob = json.dumps(data).replace("</", "<\\/")
	(out / "comparison.html").write_text(template.replace("__DATA__", blob), encoding="utf-8")


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--runs", required=True, type=Path)
	ap.add_argument("--out", required=True, type=Path)
	ap.add_argument("--workflow-run", default="")
	ap.add_argument(
		"--reference",
		type=float,
		default=0.8,
		help="the comparison bar: with --reference-mode relative (default), a fraction of the reference "
		"solution's score on each task; with absolute, a score from 0 to 1. comparison.html has a slider for it.",
	)
	ap.add_argument("--reference-mode", choices=["relative", "absolute"], default="relative")
	opts = ap.parse_args(argv)
	blocks = collect(opts.runs)
	opts.out.mkdir(parents=True, exist_ok=True)
	all_rows = [r for b in blocks for r in b["rows"]]
	summary = report.summarise(all_rows) if all_rows else {"by_agent": {}, "by_agent_task": []}
	overview = []
	for b in blocks:
		if not b["rows"]:
			overview.append({"agent": b["dir"].removeprefix("run-"), "missing": True})
			continue
		name = b["rows"][0]["agent"]
		s = summary["by_agent"][name]
		page = agent_page(b, s, None, opts.workflow_run)
		(opts.out / f"{name}.md").write_text(page, encoding="utf-8")
		overview.append(
			{
				"agent": name,
				"s": s,
				"cfg": b["cfg"],
				"tokens": (
					sum(r["usage"]["input_tokens"] for r in b["rows"]),
					sum(r["usage"]["output_tokens"] for r in b["rows"]),
				),
				"list_price": _list_price(b["rows"], b["cfg"].get("_list_prices")),
				"started": b["manifest"].get("started_at", ""),
				"commit": b["manifest"].get("foames_commit", ""),
				"aider": b["aider"],
			}
		)
	with (opts.out / "results.jsonl").open("w", encoding="utf-8") as f:
		for r in all_rows:
			f.write(json.dumps(r) + "\n")
	cells = _cells(all_rows) if all_rows else []
	(opts.out / "summary.json").write_text(
		json.dumps({"summary": summary, "qualification": cells}, indent=1), encoding="utf-8"
	)
	ranked = sorted(
		(o for o in overview if not o.get("missing") and o["agent"] not in ("reference", "noop")),
		key=lambda o: -(o["s"]["quality"] or 0),
	)
	calibration = [o for o in overview if not o.get("missing") and o["agent"] in ("reference", "noop")]
	reference = reference_scores(all_rows)
	task_ids = sorted({r["task"] for r in all_rows})
	by_agent_task = {}
	for r in all_rows:
		by_agent_task.setdefault((r["agent"], r["task"]), []).append(r)
	for o in ranked + calibration:
		o["cleared"] = sum(
			clears(by_agent_task.get((o["agent"], t), []), t, reference, opts.reference, opts.reference_mode)
			for t in task_ids
		)
	bar_text = (
		f"{opts.reference:.0%} of the reference solution's quality on each task"
		if opts.reference_mode == "relative"
		else f"quality of at least {opts.reference:.2f}"
	)
	entries = [
		{
			"agent": o["agent"],
			"model": o["s"]["model"] or "",
			"tier": o["s"]["tier"] or "calibration",
			"tokens_in": o["tokens"][0],
			"tokens_out": o["tokens"][1],
			"cost": _money(o["s"]["total_cost_usd"]),
			"list_price": _money(o["list_price"]),
			"ecl": None,
			"tasks": {
				t: [
					{**{m: r["scores"][m] for m in METRICS}, "invariants_ok": r["scores"]["invariants_kept"]}
					for r in by_agent_task.get((o["agent"], t), [])
				]
				for t in task_ids
			},
		}
		for o in ranked + [c for c in calibration if c["agent"] == "noop"]
	]
	everyone = ranked + calibration
	commits = sorted({o["commit"] for o in everyone if o["commit"]})
	lines = [
		"# FoaMES agent benchmark results",
		"",
		"<!-- SPDX-License-Identifier: Apache-2.0 -->",
		"",
		f"Runs started {min((o['started'] for o in everyone if o['started']), default='n/a')} (UTC) on FoaMES commit(s) "
		+ ", ".join(f"`{c[:10]}`" for c in commits)
		+ (f". Workflow run: {opts.workflow_run}" if opts.workflow_run else "")
		+ ".",
		"",
		"Every agent ran the six pure tasks in the benchmark's Docker sandbox on a GitHub-hosted runner "
		"(4 vCPU, 16 GB, no GPU). Hosted models were called on GitHub Models' free tier; local models were "
		"served by Ollama on the runner's CPU. Ranking is by quality (correctness and process, without cost), as in "
		"[docs/methodology.md](../../docs/methodology.md). One repetition cannot separate close agents; read the "
		"intervals.",
		"",
		f"**Reference bar: {bar_text}**, and every invariant kept. \"Clears\" counts the tasks where every "
		"repetition reached it. Move the bar with the slider in [comparison.html](comparison.html) (open the "
		"file in a browser), or rebuild with `--reference`.",
		"",
		"| Agent | Model | Tier | Runs | Clears bar | Success (95 % CI) | Quality | Composite | Mean time | Tokens in / out | Cost | List-price equivalent | ECL tier |",
		"| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
	]
	for o in ranked + calibration:
		s = o["s"]
		lines.append(
			f"| [{o['agent']}]({o['agent']}.md) | `{s['model'] or '-'}` | {s['tier'] or 'calibration'} | {s['runs']} | {o['cleared']} / {len(task_ids)} | {_pct(s['success_rate'])} {_ci(s)} | "
			f"{_num(s['quality'])} | {_num(s['composite'])} | {_num(s['mean_seconds'], '{:.0f} s')} | "
			f"{o['tokens'][0]:,} / {o['tokens'][1]:,} | {_money(s['total_cost_usd'])} | {_money(o['list_price'])} | n/a |"
		)
	for o in overview:
		if o.get("missing"):
			lines.append(f"| {o['agent']} | | | 0 | | no results (the job failed before grading) | | | | | | | |")
	tasks = sorted({r["task"] for r in all_rows})
	if tasks:
		lines += ["", "## Quality by task", "", "| Agent | " + " | ".join(tasks) + " |", "| --- |" + " ---: |" * len(tasks)]
		by = {(x["agent"], x["task"]): x for x in summary["by_agent_task"]}
		for o in ranked + calibration:
			cells_row = []
			for t in tasks:
				x = by.get((o["agent"], t))
				cells_row.append("" if not x else f"{x['quality']:.2f} {'PASS' if x['success_rate'] == 1 else ('fail' if not x['success_rate'] else _pct(x['success_rate']))}")
			lines.append(f"| {o['agent']} | " + " | ".join(cells_row) + " |")
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
			"No agent qualified for any cell: a cell needs every repetition of its qualifying tasks to succeed "
			"with mean quality at or above the cell's minimum (data/recommendations.json)."
		)
	lines += [
		"",
		"## Notes",
		"",
		f"- {ECL_NOTE}",
		"- Cost is what the runs cost: $0 on GitHub Models' free tier and for local models (electricity and runner "
		"time are not counted). The list-price equivalent prices the same tokens at the provider's paid list price "
		"(agents.json `_list_prices`).",
		"- Aider prints token counts rounded to the nearest hundred above 1,000, so token totals are approximate.",
		"- GitHub Models' free tier caps each request at about 8,000 input tokens. Aider's repository map was "
		"kept at 512 tokens for those agents, and a model that asks to read a large file such as AGENTS.md can hit "
		"the cap. That is a limit of the free tier, not of the model.",
		"- Local models ran on CPU only. The recommended open-weight models in the matrix (Qwen3-Coder 30B, "
		"gpt-oss 20b and up) need more memory or a GPU than a hosted runner has; the small coder models here are a "
		"floor for the open-weight tier, not its ceiling.",
		f"- Versions: {', '.join(sorted({o['aider'] for o in ranked if o['aider']})) or 'see the per-agent pages'}.",
		"",
	]
	(opts.out / "README.md").write_text("\n".join(lines), encoding="utf-8")
	write_html(
		opts.out,
		entries,
		reference,
		task_ids,
		opts.reference,
		opts.reference_mode,
		lines[4].replace("`", ""),
		"Bar applies per task: in relative mode the reference solution's own score on that task is 100 %. "
		"Ranked by tasks cleared, then mean score. Data: results.jsonl in this folder. "
		"See benchmarks/docs/methodology.md for the scoring.",
	)
	print(f"wrote {opts.out} ({len(all_rows)} runs, {len(ranked)} agents)")


if __name__ == "__main__":
	main()
