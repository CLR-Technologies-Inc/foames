# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Statistical process control over machine measurements. No Frappe dependency.

Shewhart charts for variables data: individuals and moving range (I-MR) for one reading at a time,
and X-bar and R for readings grouped into rational subgroups of a fixed size. The run rules are the
eight Nelson rules and the four Western Electric zone rules. `findings` turns signals on recent
readings into Agent Suggestion dicts, the same shape the rules in `suggestions.py` return.

The chart factors and the I-MR / X-bar R arithmetic follow CLR Technologies' ops-library
(02-quality-and-statistics/tools/python/opex_stats), extended here with the zone rules and with
limits taken from a baseline so new readings are judged against past behaviour, not their own.
"""

from __future__ import annotations

import math
import statistics
from functools import cache
from itertools import pairwise

MIN_BASELINE_POINTS = 20
DEFAULT_SUBGROUP_SIZE = 5
MAX_SUBGROUP_SIZE = 25

# d3, the standard deviation of the relative range W = R / sigma (ASTM E2587 / AIAG SPC manual).
_D3_TABLE = {
	2: 0.8525,
	3: 0.8884,
	4: 0.8798,
	5: 0.8641,
	6: 0.8480,
	7: 0.8332,
	8: 0.8198,
	9: 0.8078,
	10: 0.7971,
	11: 0.7873,
	12: 0.7785,
	13: 0.7704,
	14: 0.7630,
	15: 0.7562,
	16: 0.7499,
	17: 0.7441,
	18: 0.7386,
	19: 0.7335,
	20: 0.7287,
	21: 0.7242,
	22: 0.7199,
	23: 0.7159,
	24: 0.7121,
	25: 0.7084,
}

# rule id -> (short name, what it means on the floor)
RULES = {
	"N1": ("Beyond 3 sigma", "one point outside the control limits"),
	"N2": ("Shift", "nine points in a row on one side of the centre line"),
	"N3": ("Trend", "six points in a row steadily increasing or decreasing"),
	"N4": ("Oscillation", "fourteen points in a row alternating up and down"),
	"N5": ("2 of 3 beyond 2 sigma", "two of three points in a row beyond 2 sigma on the same side"),
	"N6": ("4 of 5 beyond 1 sigma", "four of five points in a row beyond 1 sigma on the same side"),
	"N7": ("Stratification", "fifteen points in a row within 1 sigma of the centre line"),
	"N8": ("Mixture", "eight points in a row beyond 1 sigma on either side, none within"),
	"WE1": ("Beyond 3 sigma", "one point outside the control limits"),
	"WE2": ("2 of 3 beyond 2 sigma", "two of three points in a row beyond 2 sigma on the same side"),
	"WE3": ("4 of 5 beyond 1 sigma", "four of five points in a row beyond 1 sigma on the same side"),
	"WE4": ("Shift", "eight points in a row on one side of the centre line"),
}
RULE_SETS = {
	"Nelson": ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8"),
	"Western Electric": ("WE1", "WE2", "WE3", "WE4"),
}
SEVERITY = {"N1": "Critical", "WE1": "Critical"}


# ------------------------------------------------------------------ chart factors


def _phi(x: float) -> float:
	return 0.5 * math.erfc(-x / math.sqrt(2.0))


@cache
def d2(n: int) -> float:
	"""Expected relative range of n standard normal values, by Simpson's rule."""
	if n < 2:
		raise ValueError("subgroup size must be at least 2")
	lo, hi, steps = -10.0, 10.0, 4000
	h = (hi - lo) / steps
	total = 0.0
	for i in range(steps + 1):
		p = _phi(lo + i * h)
		weight = 1 if i in (0, steps) else (4 if i % 2 else 2)
		total += weight * (1.0 - (1.0 - p) ** n - p**n)
	return total * h / 3.0


@cache
def factors(n: int) -> dict:
	"""d2, d3, A2, D3 and D4 for subgroup size n (2 to 25)."""
	if n not in _D3_TABLE:
		raise ValueError(f"subgroup size must be between 2 and {MAX_SUBGROUP_SIZE}")
	_d2, _d3 = d2(n), _D3_TABLE[n]
	return {
		"n": n,
		"d2": _d2,
		"d3": _d3,
		"A2": 3.0 / (_d2 * math.sqrt(n)),
		"D3": max(0.0, 1.0 - 3.0 * _d3 / _d2),
		"D4": 1.0 + 3.0 * _d3 / _d2,
	}


# ---------------------------------------------------------------------- run rules


def _rule_ids(rules) -> tuple[str, ...]:
	if isinstance(rules, str):
		if rules not in RULE_SETS:
			raise ValueError(f"unknown rule set {rules!r}; use one of {', '.join(RULE_SETS)}")
		return RULE_SETS[rules]
	unknown = [r for r in rules if r not in RULES]
	if unknown:
		raise ValueError(f"unknown rules {unknown}")
	return tuple(rules)


def _runs(n: int, length: int, test) -> list[int]:
	"""Indices i where test(i - length + 1 .. i) holds."""
	return [i for i in range(length - 1, n) if test(i - length + 1, i + 1)]


def _k_of_m(z: list[float], k: int, m: int, beyond: float) -> list[int]:
	"""Indices ending a window of m points where k or more lie beyond `beyond` sigma on one side,
	the last point among them (so a signal lands on the point that completes the pattern)."""
	out = []
	for i in range(k - 1, len(z)):
		window = z[max(0, i - m + 1) : i + 1]
		for side in (1, -1):
			if side * z[i] > beyond and sum(1 for v in window if side * v > beyond) >= k:
				out.append(i)
				break
	return out


def run_rules(points, cl: float, ucl: float, lcl: float, rules="Nelson") -> list[dict]:
	"""Signals as [{"index", "rule", "name", "description"}], sorted by index then rule.

	Zones are measured in sigma = (ucl - cl) / 3, so the limits must be symmetric 3-sigma limits for
	rules other than N1 / WE1. A point exactly on a limit or the centre line counts as inside it."""
	points = [float(p) for p in points]
	n = len(points)
	ids = _rule_ids(rules)
	sigma = (ucl - cl) / 3.0
	z = [(p - cl) / sigma for p in points] if sigma > 0 else None
	diffs = [b - a for a, b in pairwise(points)]
	hits: list[tuple[int, str]] = []

	def side_run(length):
		return _runs(
			n,
			length,
			lambda a, b: all(p > cl for p in points[a:b]) or all(p < cl for p in points[a:b]),
		)

	for rule in ids:
		if rule in ("N1", "WE1"):
			found = [i for i, p in enumerate(points) if p > ucl or p < lcl]
		elif rule == "N2":
			found = side_run(9)
		elif rule == "WE4":
			found = side_run(8)
		elif rule == "N3":
			# six points means five consecutive differences of one sign
			found = [
				i
				for i in range(5, n)
				if all(d > 0 for d in diffs[i - 5 : i]) or all(d < 0 for d in diffs[i - 5 : i])
			]
		elif rule == "N4":
			found = [
				i
				for i in range(13, n)
				if all(d != 0 for d in diffs[i - 13 : i])
				and all((diffs[k] > 0) != (diffs[k + 1] > 0) for k in range(i - 13, i - 1))
			]
		elif z is None:
			found = []  # no spread, so no zones
		elif rule in ("N5", "WE2"):
			found = _k_of_m(z, 2, 3, 2.0)
		elif rule in ("N6", "WE3"):
			found = _k_of_m(z, 4, 5, 1.0)
		elif rule == "N7":
			found = _runs(n, 15, lambda a, b: all(abs(v) < 1.0 for v in z[a:b]))
		elif rule == "N8":
			found = _runs(n, 8, lambda a, b: all(abs(v) > 1.0 for v in z[a:b]))
		else:  # pragma: no cover - _rule_ids rejects anything else
			found = []
		hits.extend((i, rule) for i in found)

	return [
		{"index": i, "rule": rule, "name": RULES[rule][0], "description": RULES[rule][1]}
		for i, rule in sorted(hits, key=lambda h: (h[0], ids.index(h[1])))
	]


# ------------------------------------------------------------------------- charts


def _chart(name, points, cl, ucl, lcl, signals) -> dict:
	return {"chart": name, "points": points, "cl": cl, "ucl": ucl, "lcl": lcl, "signals": signals}


def imr_chart(values, baseline: int | None = None, rules="Nelson") -> dict:
	"""Individuals and moving range charts. Limits come from the first `baseline` values (all of
	them when None); every value is then judged against those limits. Moving ranges overlap, so only
	the beyond-the-limit rule applies to the MR chart."""
	values = [float(v) for v in values]
	base = values[: baseline or len(values)]
	if len(base) < 2:
		raise ValueError("an I-MR chart needs at least two baseline values")
	f = factors(2)
	mr = [abs(b - a) for a, b in pairwise(values)]
	base_mr = [abs(b - a) for a, b in pairwise(base)]
	mr_bar = statistics.fmean(base_mr)
	x_bar = statistics.fmean(base)
	sigma = mr_bar / f["d2"]
	ucl, lcl = x_bar + 3 * sigma, x_bar - 3 * sigma
	mr_ucl, mr_lcl = f["D4"] * mr_bar, f["D3"] * mr_bar
	beyond = ("N1",) if "N1" in _rule_ids(rules) else ("WE1",)
	return {
		"individuals": _chart("I", values, x_bar, ucl, lcl, run_rules(values, x_bar, ucl, lcl, rules)),
		"moving_range": _chart(
			"MR", mr, mr_bar, mr_ucl, mr_lcl, run_rules(mr, mr_bar, mr_ucl, mr_lcl, beyond)
		),
		"sigma_within": sigma,
		"baseline_points": len(base),
	}


def subgroups_of(values, size: int) -> list[list[float]]:
	"""Consecutive readings in groups of `size`; a short trailing group is left out."""
	values = [float(v) for v in values]
	return [values[i : i + size] for i in range(0, len(values) - size + 1, size)]


def xbar_r_chart(subgroups, baseline: int | None = None, rules="Nelson") -> dict:
	"""X-bar and R charts for equal-size subgroups (2 to 25 readings each). Limits come from the
	first `baseline` subgroups (all of them when None); only the beyond-the-limit rule applies to R."""
	if not subgroups:
		raise ValueError("an X-bar R chart needs at least one subgroup")
	n = len(subgroups[0])
	if any(len(s) != n for s in subgroups):
		raise ValueError("subgroups must all be the same size")
	f = factors(n)
	means = [statistics.fmean(s) for s in subgroups]
	ranges = [max(s) - min(s) for s in subgroups]
	count = baseline or len(subgroups)
	x_dbar = statistics.fmean(means[:count])
	r_bar = statistics.fmean(ranges[:count])
	ucl, lcl = x_dbar + f["A2"] * r_bar, x_dbar - f["A2"] * r_bar
	r_ucl, r_lcl = f["D4"] * r_bar, f["D3"] * r_bar
	beyond = ("N1",) if "N1" in _rule_ids(rules) else ("WE1",)
	return {
		"xbar": _chart("Xbar", means, x_dbar, ucl, lcl, run_rules(means, x_dbar, ucl, lcl, rules)),
		"range": _chart("R", ranges, r_bar, r_ucl, r_lcl, run_rules(ranges, r_bar, r_ucl, r_lcl, beyond)),
		"sigma_within": r_bar / f["d2"],
		"baseline_points": min(count, len(subgroups)),
	}


# ----------------------------------------------------------------------- findings


def _fmt(x: float) -> str:
	return f"{x:.6g}"


def findings(
	series: dict,
	recent_from=None,
	rules="Nelson",
	subgroup_size: int = 0,
	min_baseline: int = MIN_BASELINE_POINTS,
) -> list[dict]:
	"""Agent Suggestion dicts for signals on recent readings of one machine measurement.

	`series` is {"machine", "measurement", "readings": [(timestamp, value), ...]} in time order.
	Readings before `recent_from` form the baseline that sets the limits; signals are reported only
	on readings at or after it (on every reading when `recent_from` is None, with limits from all).
	`subgroup_size` 2..25 adds an X-bar R chart over consecutive readings; 0 or 1 means I-MR only.
	One finding per chart and rule, with the latest signalled reading as evidence. The rule_key has
	no timestamp, so a signal that persists does not pile up suggestions; the caller decides whether
	a resolved suggestion reopens (see `latest_signal_at` in the evidence)."""
	readings = [(t, float(v)) for t, v in series.get("readings") or [] if v is not None]
	machine, measurement = series["machine"], series["measurement"]
	if recent_from is None:
		baseline = len(readings)
	else:
		baseline = sum(1 for t, _ in readings if t < recent_from)
	out = []
	charts = []
	if baseline >= max(min_baseline, 2) and len(readings) > (0 if recent_from is None else baseline):
		imr = imr_chart([v for _, v in readings], baseline=baseline, rules=rules)
		times = [t for t, _ in readings]
		charts.append(("I", imr["individuals"], times, imr["sigma_within"], baseline))
		charts.append(("MR", imr["moving_range"], times[1:], imr["sigma_within"], baseline))
	if subgroup_size and subgroup_size >= 2:
		groups = subgroups_of([v for _, v in readings], subgroup_size)
		ends = [readings[(k + 1) * subgroup_size - 1][0] for k in range(len(groups))]
		base_groups = baseline // subgroup_size
		if base_groups >= max(math.ceil(min_baseline / subgroup_size), 2) and groups:
			xr = xbar_r_chart(groups, baseline=base_groups, rules=rules)
			charts.append(("X-bar", xr["xbar"], ends, xr["sigma_within"], base_groups))
			charts.append(("R", xr["range"], ends, xr["sigma_within"], base_groups))

	for chart_name, chart, times, sigma, base_count in charts:
		by_rule: dict[str, list[int]] = {}
		for s in chart["signals"]:
			if recent_from is None or times[s["index"]] >= recent_from:
				by_rule.setdefault(s["rule"], []).append(s["index"])
		for rule, indices in by_rule.items():
			last = indices[-1]
			name, description = RULES[rule]
			value = chart["points"][last]
			out.append(
				{
					"rule_key": f"spc:{machine}:{measurement}:{chart_name}:{rule}",
					"category": "Quality",
					"severity": SEVERITY.get(rule, "Warning"),
					"title": f"{measurement} on {machine} is out of control: {name} ({chart_name} chart)",
					"suggestion": (
						f"The {chart_name} chart of {measurement} on {machine} shows {description} "
						f"({rule}), most recently at {times[last]} with {_fmt(value)} against centre "
						f"{_fmt(chart['cl'])} and limits {_fmt(chart['lcl'])} to {_fmt(chart['ucl'])}. "
						"Look for an assignable cause (material lot, tool wear, setup, operator, sensor "
						"drift) before adjusting the process."
					),
					"reference_doctype": "Machine",
					"reference_name": machine,
					"evidence": {
						"machine": machine,
						"measurement": measurement,
						"chart": chart_name,
						"rule": rule,
						"rule_name": name,
						"signal_count": len(indices),
						"latest_signal_at": str(times[last]),
						"latest_value": value,
						"signals": [
							{"at": str(times[i]), "value": chart["points"][i]} for i in indices[-10:]
						],
						"centre_line": chart["cl"],
						"ucl": chart["ucl"],
						"lcl": chart["lcl"],
						"sigma_within": sigma,
						"baseline_points": base_count,
						"subgroup_size": subgroup_size if chart_name in ("X-bar", "R") else 1,
					},
				}
			)
	return out
