# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0
"""Rewrite the agent benchmark summary in the repository README.

  python benchmarks/scripts/readme_status.py [--readme README.md]

One row per benchmark agent in agents.json (the aider agents and the Claude Code model agents), grouped
by provider: what the model was built for, the latest dated report it appears in, its pass rate and the
ECL it reached, or why it has not run (a skip reason from agents.json, or a note in
benchmarks/results/run-status.json for runs still queued). The table sits between two markers in the
README and nothing else there changes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
START, END = "<!-- bench-status:start -->", "<!-- bench-status:end -->"
PROVIDERS = [
	("claude-code", "Claude Code on a Claude subscription (this account, not the API)"),
	("gemini", "Google Gemini API, free tier"),
	("openrouter", "OpenRouter, free models"),
	("nvidia_nim", "NVIDIA Build (NIM), free development credits"),
	("groq", "Groq, free tier"),
	("mistral", "Mistral, free tier"),
	("cerebras", "Cerebras, free tier"),
	("ollama-runner", "Ollama on a GitHub-hosted runner (4 vCPU, 16 GB, CPU only)"),
	("ollama-gpu", "Ollama on a free notebook GPU (Kaggle or Colab)"),
]


def provider(a: dict) -> str:
	if a.get("harness") == "claude-code":
		return "claude-code"
	p = a.get("model", "").split("/", 1)[0]
	if p.startswith("ollama"):
		return "ollama-gpu" if a.get("_runs_on") == "gpu" else "ollama-runner"
	return p


def use(a: dict) -> str:
	u = a.get("_use", "")
	if not u:
		return "-"
	return u if u.startswith(("coding", "agentic coding")) else f"{u} (off-label)"


def latest_results(results: Path) -> dict:
	"""agent -> (report date, its summary row, ECL reached), from the newest report that ran it."""
	found = {}
	for summary in sorted(results.glob("*/summary.json")):
		d = json.loads(summary.read_text(encoding="utf-8"))
		for name, s in d.get("summary", {}).get("by_agent", {}).items():
			found[name] = (summary.parent.name, s, d.get("ecl_reached", {}).get(name))
	return found


def table(agents: list, results: dict, status: dict) -> list[str]:
	lines = []
	for key, title in PROVIDERS:
		group = [a for a in agents if provider(a) == key]
		if not group:
			continue
		lines += [
			f"**{title}**",
			"",
			"| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |",
			"| --- | --- | --- | --- | ---: | ---: | --- |",
		]
		for a in group:
			name = a["name"]
			if name in results:
				day, s, ecl = results[name]
				lines.append(
					f"| {name} | `{s.get('model') or a.get('model', '')}` | {use(a)} | "
					f"[{day}](benchmarks/results/{day}/README.md) | {s['runs']} | "
					f"{round(100 * s['success_rate'])}% | {('ECL ' + str(ecl)) if ecl else 'none'} |"
				)
			else:
				why = a.get("_skip_reason") and f"Skipped: {a['_skip_reason']}" or status.get(name)
				why = why or next(
					(v for k, v in status.items() if k.endswith("*") and name.startswith(k[:-1])), ""
				)
				model = "picked at run time" if a.get("_model_candidates") else f"`{a.get('model', '')}`"
				lines.append(f"| {name} | {model} | {use(a)} | {why or 'Not run yet'} | - | - | - |")
		lines.append("")
	return lines


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("--readme", type=Path, default=BENCH.parent / "README.md")
	opts = ap.parse_args(argv)
	agents = [
		a
		for a in json.loads((BENCH / "agents.json").read_text(encoding="utf-8"))["agents"]
		if (a["name"].startswith("aider-") and a["name"] != "aider-local")
		or (a.get("harness") == "claude-code" and a.get("_runs_on") == "subscription")
	]
	status_file = BENCH / "results" / "run-status.json"
	status = json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {}
	status.pop("_comment", None)
	intro = (
		"Each agent runs the same tasks in the [agent benchmark](benchmarks/README.md): the six core tasks, and "
		"for the Claude Code agents the 29 sector case studies. Pass rate is the share of runs whose every "
		"invariant test passed. ECL reached is the highest Equipment Complexity Level at which the agent passed "
		"every task at that level and below, among the levels its model tier may claim. Off-label models were not built for agentic "
		"coding and are here to show how far each kind gets. Free tiers and the subscription cost $0; each "
		"dated report also gives the same tokens at list price."
	)
	block = [START, "", intro, "", *table(agents, latest_results(BENCH / "results"), status), END]
	text = opts.readme.read_text(encoding="utf-8")
	if START in text:
		head, rest = text.split(START, 1)
		text = head + "\n".join(block) + rest.split(END, 1)[1]
	else:
		anchor = "## Contributing"
		text = text.replace(anchor, "## Agent benchmark results\n\n" + "\n".join(block) + "\n\n" + anchor, 1)
	opts.readme.write_text(text, encoding="utf-8")
	print(f"updated {opts.readme}")


if __name__ == "__main__":
	main()
