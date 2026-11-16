# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Equipment Complexity Level (ECL): how complex a machine is to reason about, and so which model
tier may advise on it and how much human expertise must stay in charge.

ECL 1 to 5 abstracts what a piece of equipment does into the kind of model needed for it. A torque
wrench is ECL 1; a lithography scanner is ECL 5. At ECL 4 one human expert reviews every agent
suggestion (Human Expert Recommended); at ECL 5 no current model tier is adequate and a distributed
team of experts decides (Expert Team Required). The levels match the benchmark's
`benchmarks/data/recommendations.json` "ecl" block and the public list of equipment classes at
https://github.com/CLR-Technologies-Inc/equipment-complexity-levels; a test keeps them in step.

Pure: imports nothing from Frappe. The tier floors are dated priors, not measured results.
"""

from __future__ import annotations

import re

TIER_ORDER = ("oss", "baseline", "frontier")
OVERSIGHT_ORDER = ("none", "single", "team")
HUMAN_EXPERT = "Human Expert Recommended"  # one expert
EXPERT_TEAM = "Expert Team Required"  # a distributed team of experts
OVERSIGHT_LABELS = {"none": None, "single": HUMAN_EXPERT, "team": EXPERT_TEAM}

CLASS_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LIST_URL = "https://github.com/CLR-Technologies-Inc/equipment-complexity-levels"

LEVELS: dict[int, dict] = {
	1: {
		"name": "Simple tool or apparatus",
		"examples": "torque wrench, hand gauge, timer, stirrer, scale",
		"min_tier": "oss",
		"loa": 4,
		"agent_role": "Suggests one action; a person acts",
		"oversight": "none",
	},
	2: {
		"name": "Single-function machine",
		"examples": "filler, capper, press, conveyor, packaging machine with a PLC and counters",
		"min_tier": "oss",
		"loa": 4,
		"agent_role": "Suggests one action; a person acts",
		"oversight": "none",
	},
	3: {
		"name": "Configurable multi-step machine or work cell",
		"examples": "CNC machining centre, injection moulding cell, batch reactor with recipes",
		"min_tier": "baseline",
		"loa": 4,
		"agent_role": "Suggests one action; a person acts",
		"oversight": "none",
	},
	4: {
		"name": "Coupled process equipment",
		"examples": "photomask writing and inspection, CVD or PVD chamber, bioreactor, controlled furnace",
		"min_tier": "frontier",
		"loa": 3,
		"agent_role": "Narrows the options; one expert in the equipment chooses",
		"oversight": "single",
	},
	5: {
		"name": "Frontier equipment",
		"examples": "lithography (the scanner and its process), many tightly coupled subsystems",
		"min_tier": None,
		"loa": 2,
		"agent_role": "Lists options for the expert team; decides nothing",
		"oversight": "team",
	},
}


def parse_ecl(value) -> int | None:
	"""An ECL from a field value ('', None, '3', 3); None when the machine is not rated."""
	if value in (None, "", 0, "0"):
		return None
	try:
		level = int(str(value).strip())
	except (TypeError, ValueError):
		raise ValueError(f"ECL must be 1 to 5, not {value!r}") from None
	if level not in LEVELS:
		raise ValueError(f"ECL must be 1 to 5, not {value!r}")
	return level


def tier_rank(tier: str | None) -> int:
	return TIER_ORDER.index(tier) if tier in TIER_ORDER else -1


def profile(ecl) -> dict:
	"""What an ECL means for an agent: the level, the minimum model tier, the agent's role (its
	level of automation, never above 4 in FoaMES) and the human oversight it needs."""
	level = parse_ecl(ecl)
	if level is None:
		return {
			"ecl": None,
			"rated": False,
			"name": None,
			"min_tier": None,
			"loa": None,
			"agent_role": "Not rated: rate the machine before tying an agent to it",
			"oversight": None,
			"human_oversight": None,
			"agents_allowed": False,
		}
	info = LEVELS[level]
	return {
		"ecl": level,
		"rated": True,
		"name": info["name"],
		"examples": info["examples"],
		"min_tier": info["min_tier"],
		"loa": info["loa"],
		"agent_role": info["agent_role"],
		"oversight": info["oversight"],
		"human_oversight": OVERSIGHT_LABELS[info["oversight"]],
		"agents_allowed": info["min_tier"] is not None,
	}


def eligibility(tier: str | None, ecl) -> dict:
	"""Whether an agent of `tier` (oss, baseline or frontier) may be tied to equipment of `ecl`.

	An agent qualifies only when the machine is rated, the level has an adequate tier, and the
	agent's tier meets it. Qualifying never removes the human oversight the level needs."""
	info = profile(ecl)
	out = {
		"tier": tier,
		"ecl": info["ecl"],
		"min_tier": info["min_tier"],
		"oversight": info["oversight"],
		"human_oversight": info["human_oversight"],
		"loa": info["loa"],
	}
	if tier is not None and tier not in TIER_ORDER:
		raise ValueError(f"tier must be one of {', '.join(TIER_ORDER)}, not {tier!r}")
	if not info["rated"]:
		return {**out, "eligible": False, "reason": "The machine has no ECL yet"}
	if info["min_tier"] is None:
		return {
			**out,
			"eligible": False,
			"reason": f"No model tier is adequate at ECL {info['ecl']}: {EXPERT_TEAM}. "
			"An agent may only list options for the expert team",
		}
	if tier is None:
		return {
			**out,
			"eligible": None,
			"reason": f"Give a tier; ECL {info['ecl']} needs {info['min_tier']} or above",
		}
	if tier_rank(tier) < tier_rank(info["min_tier"]):
		return {
			**out,
			"eligible": False,
			"reason": f"Tier {tier} is below the ECL {info['ecl']} minimum, {info['min_tier']}",
		}
	reason = f"Tier {tier} meets the ECL {info['ecl']} minimum, {info['min_tier']}"
	if info["human_oversight"]:
		reason += f"; {info['human_oversight']}"
	return {**out, "eligible": True, "reason": reason}


def group_ecl(levels) -> int | None:
	"""The ECL of a line or work centre: that of its most complex rated member."""
	rated = [lvl for lvl in (parse_ecl(v) for v in levels) if lvl is not None]
	return max(rated) if rated else None


def combined_oversight(*oversights: str | None) -> str:
	"""The stricter of several oversight needs (none, single, team), for example a machine's ECL
	oversight and the oversight of the material it runs (its MPC)."""
	ranks = [OVERSIGHT_ORDER.index(o) for o in oversights if o in OVERSIGHT_ORDER]
	return OVERSIGHT_ORDER[max(ranks)] if ranks else "none"


def mpc_oversight(mpc) -> str:
	"""The oversight a Material Processing Complexity level needs, which follows ECL's pattern:
	none at 1 to 3, one expert at 4, a team of experts at 5."""
	try:
		level = int(mpc)
	except (TypeError, ValueError):
		return "none"
	return "team" if level >= 5 else "single" if level == 4 else "none"


def valid_class_id(class_id: str | None) -> bool:
	return bool(class_id) and bool(CLASS_ID.match(class_id)) and len(class_id) <= 80


def rating_from_class(entry: dict) -> dict:
	"""A proposed rating from one entry of the public ECL list. Entries reviewed only by
	`ai-initial` are drafts: the result says so, and a person decides whether to adopt it."""
	level = parse_ecl(entry.get("ecl"))
	if level is None:
		raise ValueError(f"list entry {entry.get('id')!r} has no ECL")
	reviewed_by = entry.get("reviewed_by") or "ai-initial"
	return {
		"ecl": level,
		"ecl_class": entry.get("id"),
		"name": entry.get("name"),
		"rationale": entry.get("ecl_rationale"),
		"confidence": entry.get("confidence"),
		"reviewed_by": reviewed_by,
		"draft": reviewed_by == "ai-initial",
		"oversight": LEVELS[level]["oversight"],
		"source": LIST_URL,
	}
