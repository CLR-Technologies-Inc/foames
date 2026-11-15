# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Which model tier to start with for a project's TRL and process complexity, and, given benchmark
results, which of your agents actually qualifies for that cell and at what cost."""

import json
from collections import defaultdict
from statistics import fmean

from foames_bench.paths import DATA_DIR

TRL_BANDS = ("1-3", "4-6", "7-9")
COMPLEXITIES = ("low", "medium", "high")


def load() -> dict:
	return json.loads((DATA_DIR / "recommendations.json").read_text(encoding="utf-8"))


def band(trl: int) -> str:
	if not 1 <= trl <= 9:
		raise ValueError("TRL runs from 1 to 9")
	return TRL_BANDS[(trl - 1) // 3]


def cell(trl: int, complexity: str) -> dict:
	if complexity not in COMPLEXITIES:
		raise ValueError(f"complexity is one of {', '.join(COMPLEXITIES)}")
	data = load()
	return {
		"band": band(trl),
		"complexity": complexity,
		**data["cells"][band(trl)][complexity],
		"as_of": data["as_of"],
	}


def qualify(rows: list[dict], recommendation: dict) -> list[dict]:
	"""Agents ranked for one cell from benchmark rows: an agent qualifies when it ran every
	qualifying task, its mean quality there reaches the cell's minimum, and every repetition of
	every qualifying task succeeded. Qualified agents are ordered by cost per success, then quality."""
	wanted = set(recommendation["qualify_with"])
	by_agent = defaultdict(list)
	for r in rows:
		if r["task"] in wanted:
			by_agent[r["agent"]].append(r)
	ranked = []
	for agent, rs in by_agent.items():
		tasks_run = {r["task"] for r in rs}
		quality = fmean(r["scores"]["quality"] for r in rs)
		all_success = all(r["scores"]["success"] for r in rs)
		costs = [r["usage"]["cost_usd"] for r in rs]
		cost = sum(costs) if all(c is not None for c in costs) else None
		successes = sum(r["scores"]["success"] for r in rs)
		ranked.append(
			{
				"agent": agent,
				"model": rs[0]["model"],
				"tier": rs[0]["agent_tier"],
				"runs": len(rs),
				"missing_tasks": sorted(wanted - tasks_run),
				"quality": round(quality, 3),
				"all_reps_succeeded": all_success,
				"cost_per_success_usd": round(cost / successes, 4)
				if cost is not None and successes
				else None,
				"qualifies": not (wanted - tasks_run)
				and all_success
				and quality >= recommendation["min_quality"],
			}
		)
	ranked.sort(
		key=lambda a: (
			not a["qualifies"],
			a["cost_per_success_usd"] if a["cost_per_success_usd"] is not None else float("inf"),
			-a["quality"],
		)
	)
	return ranked


def matrix_markdown() -> str:
	data = load()
	tiers = data["tiers"]
	lines = [
		f"Prior recommendations as of {data['as_of']} (review by {data['review_by']}). Primary tier, then alternative.",
		"",
		"| TRL band | " + " | ".join(f"{c} complexity" for c in COMPLEXITIES) + " |",
		"| --- | --- | --- | --- |",
	]
	for b in TRL_BANDS:
		cells = []
		for c in COMPLEXITIES:
			x = data["cells"][b][c]
			alt = tiers[x["alternative"]]["label"] if x["alternative"] else "none"
			cells.append(f"**{tiers[x['primary']]['label']}** (alt: {alt}); min quality {x['min_quality']}")
		lines.append(f"| {b} | " + " | ".join(cells) + " |")
	return "\n".join(lines) + "\n"
