# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tech transfer packages and comparability, the MSAT core. No Frappe dependency.

A tech transfer package describes a process well enough for a receiving site (or a larger scale)
to run it: each process parameter with its set point, normal operating range (NOR) and proven
acceptable range (PAR) and whether it is critical (CPP), key (KPP) or not; each quality attribute
with its acceptance limits and whether it is critical (CQA); and how comparability of the
receiving site's batches to the sending site's will be judged.

`package_problems` checks the package is internally consistent before it is approved (the NOR
lies inside the PAR, the set point inside the NOR, every CQA has limits and an approach).
`assess_comparability` judges one attribute from batch results of both sites, with one of the
approaches in common use (ICH Q5E; FDA's statistical approaches for analytical similarity):

- Equivalence (TOST): the 90 % confidence interval of the difference in means (receiving minus
  sending, Welch) lies inside +/- the equivalence margin. Two one-sided tests at alpha 0.05.
- Quality Range: at least `coverage` percent of receiving batches lie within the sending mean
  +/- k standard deviations (k = 3 by default).
- Min-Max: every receiving batch lies within the range the sending site has shown.
- Descriptive: summaries only; the reviewer judges.

Whatever the approach, a receiving batch outside the attribute's acceptance limits makes the
attribute Not Comparable. The outcome is evidence for the people who approve the transfer.
"""

from __future__ import annotations

import math

from foames.foames_lifesci import stats

LIMITS = ("Lower and Upper", "Lower Only", "Upper Only", "None")
PARAMETER_CRITICALITY = ("CPP", "KPP", "Non-critical")
ATTRIBUTE_CRITICALITY = ("CQA", "Non-critical")
APPROACHES = ("Equivalence (TOST)", "Quality Range", "Min-Max", "Descriptive")
SCALE_RULES = (
	"Scale Independent",
	"Linear with Volume",
	"Constant P/V",
	"Constant Tip Speed",
	"Constant kLa",
	"Constant vvm",
	"Constant Superficial Gas Velocity",
	"Constant Residence Time",
	"Other (Justify)",
)
OUTCOMES = ("Comparable", "Not Comparable", "Insufficient Data", "Descriptive Only")
DEFAULT_K = 3.0
DEFAULT_COVERAGE = 90.0
ALPHA = 0.05


def _has_lower(limits: str | None) -> bool:
	return limits in ("Lower and Upper", "Lower Only")


def _has_upper(limits: str | None) -> bool:
	return limits in ("Lower and Upper", "Upper Only")


def within(value: float, limits: str | None, lower: float | None, upper: float | None) -> bool:
	if _has_lower(limits) and value < (lower or 0.0):
		return False
	if _has_upper(limits) and value > (upper or 0.0):
		return False
	return True


def parameter_problems(p: dict) -> list[str]:
	name = p.get("parameter") or f"row {p.get('idx', '?')}"
	problems = []
	limits = p.get("limits") or "None"
	critical = p.get("criticality") in ("CPP", "KPP")
	if critical and limits == "None":
		problems.append(
			f"{name}: a {p['criticality']} needs a normal operating range and a proven acceptable range"
		)
	lo, hi = p.get("nor_low"), p.get("nor_high")
	plo, phi = p.get("par_low"), p.get("par_high")
	if limits == "Lower and Upper":
		if lo is not None and hi is not None and lo > hi:
			problems.append(f"{name}: NOR low is above NOR high")
		if plo is not None and phi is not None and plo > phi:
			problems.append(f"{name}: PAR low is above PAR high")
	if _has_lower(limits) and lo is not None and plo is not None and lo < plo:
		problems.append(f"{name}: the NOR must lie inside the PAR (NOR low {lo} < PAR low {plo})")
	if _has_upper(limits) and hi is not None and phi is not None and hi > phi:
		problems.append(f"{name}: the NOR must lie inside the PAR (NOR high {hi} > PAR high {phi})")
	sp = p.get("set_point")
	if sp is not None and p.get("has_set_point", True) and not within(sp, limits, lo, hi):
		problems.append(f"{name}: the set point {sp} is outside the NOR")
	if p.get("scale_dependent") and not p.get("scale_rule"):
		problems.append(f"{name}: a scale-dependent parameter needs a scale rule")
	if p.get("scale_rule") == "Other (Justify)" and not (p.get("justification") or "").strip():
		problems.append(f"{name}: an 'Other' scale rule needs a justification")
	return problems


def attribute_problems(a: dict) -> list[str]:
	name = a.get("attribute") or f"row {a.get('idx', '?')}"
	problems = []
	limits = a.get("limits") or "None"
	if a.get("criticality") == "CQA":
		if limits == "None":
			problems.append(f"{name}: a CQA needs acceptance limits")
		if not a.get("approach"):
			problems.append(f"{name}: a CQA needs a comparability approach")
		if not a.get("analytical_method"):
			problems.append(f"{name}: a CQA needs the analytical method that measures it")
	if limits == "Lower and Upper" and (a.get("lower") or 0.0) > (a.get("upper") or 0.0):
		problems.append(f"{name}: the lower limit is above the upper limit")
	if a.get("approach") == "Equivalence (TOST)" and not (a.get("margin") or 0) > 0:
		problems.append(f"{name}: equivalence testing needs a positive equivalence margin")
	if a.get("approach") == "Quality Range" and a.get("k") is not None and a["k"] <= 0:
		problems.append(f"{name}: the quality range multiplier k must be positive")
	return problems


def package_problems(parameters: list[dict], attributes: list[dict]) -> list[str]:
	problems = []
	for kind, rows, key in (("parameter", parameters, "parameter"), ("attribute", attributes, "attribute")):
		names = [r.get(key) for r in rows if r.get(key)]
		for dup in sorted({n for n in names if names.count(n) > 1}):
			problems.append(f"The {kind} {dup} is listed twice")
	for p in parameters:
		problems.extend(parameter_problems(p))
	for a in attributes:
		problems.extend(attribute_problems(a))
	if not any(a.get("criticality") == "CQA" for a in attributes):
		problems.append("The package names no critical quality attribute")
	return problems


def scale_ratio(from_volume: float | None, to_volume: float | None) -> float | None:
	if not from_volume or not to_volume or from_volume <= 0 or to_volume <= 0:
		return None
	return to_volume / from_volume


def _summary(values: list[float]) -> dict:
	return {
		"n": len(values),
		"mean": stats.mean(values) if values else None,
		"sd": stats.stdev(values) if len(values) > 1 else None,
		"min": min(values) if values else None,
		"max": max(values) if values else None,
	}


def assess_comparability(
	sending: list[float],
	receiving: list[float],
	approach: str,
	*,
	margin: float | None = None,
	k: float | None = None,
	coverage: float | None = None,
	limits: str | None = None,
	lower: float | None = None,
	upper: float | None = None,
	alpha: float = ALPHA,
) -> dict:
	"""Judge one attribute from sending-site and receiving-site batch results."""
	if approach not in APPROACHES:
		raise ValueError(f"unknown approach {approach!r}")
	s, r = _summary(sending), _summary(receiving)
	out_of_spec = [v for v in receiving if not within(v, limits, lower, upper)]
	result = {
		"approach": approach,
		"sending": s,
		"receiving": r,
		"out_of_spec": out_of_spec,
		"interval": None,
		"outcome": None,
		"detail": "",
	}
	minimum = {"Equivalence (TOST)": 2, "Quality Range": 2, "Min-Max": 2, "Descriptive": 1}[approach]
	if s["n"] < minimum or r["n"] < 1 or (approach == "Equivalence (TOST)" and r["n"] < 2):
		result["outcome"] = "Insufficient Data"
		result["detail"] = (
			f"{approach} needs at least {minimum} sending-site and "
			f"{2 if approach == 'Equivalence (TOST)' else 1} receiving-site results "
			f"(have {s['n']} and {r['n']})."
		)
		return result
	verdict, detail = None, ""
	if approach == "Equivalence (TOST)":
		se2 = (s["sd"] ** 2) / s["n"] + (r["sd"] ** 2) / r["n"]
		diff = r["mean"] - s["mean"]
		if se2 == 0:
			low = high = diff
			df = float("inf")
		else:
			df = se2**2 / (
				((s["sd"] ** 2 / s["n"]) ** 2) / (s["n"] - 1) + ((r["sd"] ** 2 / r["n"]) ** 2) / (r["n"] - 1)
			)
			t = stats.t_ppf(1 - alpha, df)
			half = t * math.sqrt(se2)
			low, high = diff - half, diff + half
		result["interval"] = {
			"difference": diff,
			"low": low,
			"high": high,
			"df": None if math.isinf(df) else df,
			"confidence": round(100 * (1 - 2 * alpha), 1),
			"margin": margin,
		}
		verdict = -margin < low and high < margin
		detail = (
			f"Difference in means {diff:.4g}, {result['interval']['confidence']}% CI [{low:.4g}, {high:.4g}] "
			f"{'inside' if verdict else 'not inside'} +/- {margin:.4g}."
		)
	elif approach == "Quality Range":
		k = DEFAULT_K if k is None else k
		coverage = DEFAULT_COVERAGE if coverage is None else coverage
		low, high = s["mean"] - k * s["sd"], s["mean"] + k * s["sd"]
		inside = [v for v in receiving if low <= v <= high]
		share = 100.0 * len(inside) / r["n"]
		result["interval"] = {"low": low, "high": high, "k": k, "inside_percent": share, "coverage": coverage}
		verdict = share >= coverage
		detail = (
			f"{len(inside)} of {r['n']} receiving batches ({share:.1f}%) within the sending mean +/- {k:g} SD "
			f"[{low:.4g}, {high:.4g}]; {coverage:g}% required."
		)
	elif approach == "Min-Max":
		low, high = s["min"], s["max"]
		outside = [v for v in receiving if not low <= v <= high]
		result["interval"] = {"low": low, "high": high}
		verdict = not outside
		detail = (
			f"{len(outside)} of {r['n']} receiving batches outside the sending range [{low:.4g}, {high:.4g}]."
		)
	else:
		result["outcome"] = "Descriptive Only"
		result["detail"] = "Summaries only; the reviewer judges comparability."
		if out_of_spec:
			result["detail"] += f" {len(out_of_spec)} receiving batch(es) outside the acceptance limits."
		return result
	if out_of_spec:
		verdict = False
		detail += f" {len(out_of_spec)} receiving batch(es) outside the acceptance limits."
	result["outcome"] = "Comparable" if verdict else "Not Comparable"
	result["detail"] = detail
	return result


def scale_set_point(value: float, rule: str, ratio: float) -> float | None:
	"""The receiving-scale value of a parameter that scales simply with volume, or None when the rule
	needs equipment geometry (use `scaleup.agitation` and `scaleup.aeration`) or a person's judgment."""
	if rule in ("Scale Independent", "Constant vvm", "Constant Residence Time"):
		return value
	if rule == "Linear with Volume":
		return value * ratio
	return None
