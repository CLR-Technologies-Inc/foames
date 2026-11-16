# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Which model tier to start with for a project's TRL and process complexity, optionally raised by
the Equipment Complexity Level (ECL) of the machine involved, and, given benchmark results, which of
your agents actually qualifies for that cell and at what cost."""

import json
from collections import defaultdict
from statistics import fmean

from foames_bench.paths import DATA_DIR

TRL_BANDS = ("1-3", "4-6", "7-9")
COMPLEXITIES = ("low", "medium", "high")
ECLS = (1, 2, 3, 4, 5)
TIER_ORDER = ("oss", "baseline", "frontier")
HUMAN_EXPERT = "Human Expert Recommended"


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


def ecl_level(ecl: int) -> dict:
	if ecl not in ECLS:
		raise ValueError("ECL runs from 1 to 5")
	return {"ecl": ecl, **load()["ecl"]["levels"][str(ecl)]}


def _rank(tier: str | None) -> int:
	return TIER_ORDER.index(tier) if tier in TIER_ORDER else -1


def with_ecl(rec: dict, ecl: int | None) -> dict:
	"""Apply an ECL to a TRL x complexity cell: the primary tier is raised to the ECL's minimum tier,
	an alternative below that minimum is dropped, and at ECLs flagged for a human expert the result
	says so. At an ECL with no adequate tier, no agent qualifies."""
	if ecl is None:
		return rec
	level = ecl_level(ecl)
	out = dict(rec, ecl=ecl, ecl_name=level["name"], min_tier=level["min_tier"])
	out["human_expert_recommended"] = level["human_expert_recommended"]
	if level["min_tier"] is None:
		out["primary"] = None
		out["alternative"] = None
		out["why"] = f"ECL {ecl} ({level['name']}): {level['model_note']} {rec['why']}"
	else:
		if _rank(level["min_tier"]) > _rank(rec["primary"]):
			out["primary"] = level["min_tier"]
		if rec["alternative"] and _rank(rec["alternative"]) < _rank(level["min_tier"]):
			out["alternative"] = None
	if level["human_expert_recommended"]:
		out["human_review"] = f"{HUMAN_EXPERT}. {rec['human_review']}"
	return out


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
				"below_ecl_tier": _below_ecl_tier(rs[0]["agent_tier"], recommendation),
				"qualifies": not (wanted - tasks_run)
				and all_success
				and quality >= recommendation["min_quality"]
				and not _below_ecl_tier(rs[0]["agent_tier"], recommendation),
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


def _below_ecl_tier(tier: str | None, recommendation: dict) -> bool:
	"""True when an ECL applies and the agent's tier does not reach its minimum (or no tier does)."""
	if "ecl" not in recommendation:
		return False
	if recommendation["min_tier"] is None:
		return True
	return _rank(tier) < _rank(recommendation["min_tier"])


def ecl_markdown() -> str:
	data = load()
	tiers = data["tiers"]
	lines = [
		"Equipment Complexity Level (ECL): the minimum model tier adequate for the equipment, as of "
		f"{data['as_of']}. A prior, not a benchmark result.",
		"",
		"| ECL | Equipment | Examples | USP <1058> | IEC 61508 | GAMP 5 | Minimum tier | Agent role |",
		"| --- | --- | --- | --- | --- | --- | --- | --- |",
	]
	for n in ECLS:
		x = data["ecl"]["levels"][str(n)]
		tier = tiers[x["min_tier"]]["label"] if x["min_tier"] else "none adequate"
		if x["human_expert_recommended"]:
			tier += f", **{HUMAN_EXPERT}**"
		lines.append(
			f"| {n} | {x['name']} | {x['examples']} | {x['usp_1058']} | {x['iec_61508']} | {x['gamp_5']} | {tier} | {x['agent_role']} |"
		)
	return "\n".join(lines) + "\n"


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
	return "\n".join(lines) + "\n\n" + ecl_markdown()
