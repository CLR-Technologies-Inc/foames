# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Process development (PD) simulation: designed experiments, response-surface models, Monte Carlo
what-if and design-space maps. Standard library only, no Frappe.

The methods are the textbook ones (D. C. Montgomery, Design and Analysis of Experiments; G. E. P.
Box, J. S. Hunter and W. G. Hunter, Statistics for Experimenters; ICH Q8(R2) on design space):

- Designs in coded units (-1 low, +1 high): full factorial at 2 or more levels, two-level
  fractional factorial from the standard minimum-aberration generators, and central composite
  (face-centred, alpha = 1, or rotatable, alpha = (2^k)^(1/4)), with centre points, replicates and
  a seeded run order.
- Models fitted by ordinary least squares: linear, linear with two-factor interactions, or full
  quadratic, with coefficients, standard errors, p-values, R squared, adjusted R squared and RMSE.
- What-if: factors drawn from their distributions (fixed, normal, uniform, triangular) around the
  nominal, pushed through the fitted models, with the residual error added; the result per
  response is the predicted mean, spread, percentiles, the probability of meeting its limits and
  the predicted Ppk, and the probability that every response is within limits at once.
- Design space: a grid over two factors with the others at nominal, each point marked by whether
  every response's prediction lies within its limits.

All inputs are what a person enters: the factors and their ranges, the responses and their
limits, and the results of the runs. Nothing here reads production data or changes a process.
"""

from __future__ import annotations

import itertools
import math
import random

from foames.foames_life_sciences import stats

DESIGNS = (
	"Full Factorial",
	"Fractional Factorial",
	"Central Composite (Face-Centred)",
	"Central Composite (Rotatable)",
)
MODELS = ("Linear", "Linear + Interactions", "Quadratic")
DISTRIBUTIONS = ("Fixed", "Normal", "Uniform", "Triangular")
MAX_FACTORS = 6
MAX_RESPONSES = 4
MAX_ITERATIONS = 100_000

# Minimum-aberration generators for 2^(k-p) designs (Montgomery, table 8.14). Each generator gives
# the added factor as the product of base factors (0-based indices), with the design resolution.
GENERATORS: dict[tuple[int, int], tuple[tuple[tuple[int, ...], ...], str]] = {
	(3, 1): (((0, 1),), "III"),
	(4, 1): (((0, 1, 2),), "IV"),
	(5, 1): (((0, 1, 2, 3),), "V"),
	(5, 2): (((0, 1), (0, 2)), "III"),
	(6, 1): (((0, 1, 2, 3, 4),), "VI"),
	(6, 2): (((0, 1, 2), (1, 2, 3)), "IV"),
	(6, 3): (((0, 1), (0, 2), (1, 2)), "III"),
}


def coded(value: float, low: float, high: float) -> float:
	if high == low:
		raise ValueError("a factor's low and high must differ")
	return (2.0 * value - (high + low)) / (high - low)


def actual(code: float, low: float, high: float) -> float:
	return (high + low) / 2.0 + code * (high - low) / 2.0


def _levels(n: int) -> list[float]:
	if n < 2:
		raise ValueError("a factorial needs at least two levels")
	return [-1.0 + 2.0 * i / (n - 1) for i in range(n)]


def full_factorial(k: int, levels: int = 2) -> list[list[float]]:
	# itertools.product varies the last factor fastest; reverse so the first factor varies fastest,
	# which is the standard (Yates) order.
	return [list(reversed(p)) for p in itertools.product(_levels(levels), repeat=k)]


def fractional_factorial(k: int, p: int) -> tuple[list[list[float]], str]:
	if p == 0:
		return full_factorial(k), "Full"
	if (k, p) not in GENERATORS:
		raise ValueError(f"no standard 2^({k}-{p}) design; supported: {sorted(GENERATORS)}")
	generators, resolution = GENERATORS[(k, p)]
	runs = []
	for base in full_factorial(k - p):
		runs.append(base + [math.prod(base[i] for i in gen) for gen in generators])
	return runs, resolution


def central_composite(k: int, rotatable: bool = False) -> tuple[list[list[float]], list[str], float]:
	alpha = (2**k) ** 0.25 if rotatable else 1.0
	runs = full_factorial(k)
	kinds = ["Factorial"] * len(runs)
	for i in range(k):
		for sign in (-1.0, 1.0):
			point = [0.0] * k
			point[i] = sign * alpha
			runs.append(point)
			kinds.append("Axial")
	return runs, kinds, alpha


def build_design(
	design: str,
	k: int,
	*,
	levels: int = 2,
	fraction: int = 0,
	center_points: int = 0,
	replicates: int = 1,
	randomise: bool = True,
	seed: int | None = None,
) -> dict:
	"""The run list for a design: coded settings, the point type of each run, its standard order
	and its run order."""
	if not 1 <= k <= MAX_FACTORS:
		raise ValueError(f"a design takes 1 to {MAX_FACTORS} factors")
	if replicates < 1:
		raise ValueError("replicates must be at least 1")
	if center_points < 0:
		raise ValueError("centre points cannot be negative")
	resolution, alpha = None, None
	if design == "Full Factorial":
		points = full_factorial(k, levels)
		kinds = ["Factorial"] * len(points)
	elif design == "Fractional Factorial":
		points, resolution = fractional_factorial(k, fraction)
		kinds = ["Factorial"] * len(points)
	elif design in ("Central Composite (Face-Centred)", "Central Composite (Rotatable)"):
		if k < 2:
			raise ValueError("a central composite design needs at least two factors")
		points, kinds, alpha = central_composite(k, rotatable=design.endswith("(Rotatable)"))
	else:
		raise ValueError(f"unknown design {design!r}")
	points = [p for p in points for _ in range(replicates)]
	kinds = [t for t in kinds for _ in range(replicates)]
	points += [[0.0] * k for _ in range(center_points)]
	kinds += ["Center"] * center_points
	runs = [{"std_order": i + 1, "point_type": kinds[i], "coded": points[i]} for i in range(len(points))]
	order = list(range(len(runs)))
	if randomise:
		random.Random(seed).shuffle(order)
	for run_no, i in enumerate(order, start=1):
		runs[i]["run_no"] = run_no
	runs.sort(key=lambda r: r["run_no"])
	return {"design": design, "factors": k, "runs": runs, "resolution": resolution, "alpha": alpha}


def model_terms(k: int, model: str) -> list[tuple[int, ...]]:
	"""Model terms as tuples of factor indices: () intercept, (i,) main effect, (i, j) interaction,
	(i, i) square."""
	if model not in MODELS:
		raise ValueError(f"unknown model {model!r}")
	terms: list[tuple[int, ...]] = [(), *((i,) for i in range(k))]
	if model in ("Linear + Interactions", "Quadratic"):
		terms += list(itertools.combinations(range(k), 2))
	if model == "Quadratic":
		terms += [(i, i) for i in range(k)]
	return terms


def term_label(term: tuple[int, ...], symbols: list[str]) -> str:
	if not term:
		return "Intercept"
	if len(term) == 2 and term[0] == term[1]:
		return f"{symbols[term[0]]}^2"
	return "*".join(symbols[i] for i in term)


def _row(point: list[float], terms: list[tuple[int, ...]]) -> list[float]:
	return [math.prod(point[i] for i in t) if t else 1.0 for t in terms]


def fit(points: list[list[float]], y: list[float], model: str, symbols: list[str] | None = None) -> dict:
	"""Least-squares fit of one response on coded factor settings."""
	k = len(points[0]) if points else 0
	symbols = symbols or [f"x{i + 1}" for i in range(k)]
	terms = model_terms(k, model)
	n, p = len(y), len(terms)
	if n < p:
		raise ValueError(f"a {model} model in {k} factors needs at least {p} runs with results; have {n}")
	x = [_row(pt, terms) for pt in points]
	xtx = [[sum(x[r][i] * x[r][j] for r in range(n)) for j in range(p)] for i in range(p)]
	xty = [sum(x[r][i] * y[r] for r in range(n)) for i in range(p)]
	try:
		beta = stats.solve(xtx, xty)
	except ValueError:
		raise ValueError(
			f"the design cannot estimate a {model} model (terms are aliased); choose a smaller model or another design"
		)
	fitted = [sum(b * v for b, v in zip(beta, row, strict=True)) for row in x]
	residuals = [yi - fi for yi, fi in zip(y, fitted, strict=True)]
	sse = sum(e * e for e in residuals)
	ybar = stats.mean(y)
	sst = sum((yi - ybar) ** 2 for yi in y)
	dfe = n - p
	mse = sse / dfe if dfe > 0 else None
	r2 = 1.0 - sse / sst if sst > 0 else 1.0
	adj = 1.0 - (1.0 - r2) * (n - 1) / dfe if dfe > 0 and sst > 0 else None
	coefficients = []
	inv = stats.inverse(xtx) if mse is not None else None
	for i, term in enumerate(terms):
		entry = {"term": term_label(term, symbols), "factors": list(term), "estimate": beta[i]}
		if inv is not None and mse is not None:
			se = math.sqrt(max(inv[i][i] * mse, 0.0))
			entry["std_error"] = se
			if se > 0:
				t = beta[i] / se
				entry["t"] = t
				entry["p_value"] = stats.two_sided_p(t, dfe)
		coefficients.append(entry)
	return {
		"model": model,
		"factors": k,
		"runs": n,
		"terms": [list(t) for t in terms],
		"coefficients": coefficients,
		"r_squared": r2,
		"adj_r_squared": adj,
		"rmse": math.sqrt(mse) if mse is not None else None,
		"residual_df": dfe,
		"residuals": residuals,
	}


def predict(model: dict, point: list[float]) -> float:
	terms = [tuple(t) for t in model["terms"]]
	return sum(c["estimate"] * v for c, v in zip(model["coefficients"], _row(point, terms), strict=True))


def _draw(rng: random.Random, f: dict) -> float:
	nominal = f["nominal"]
	dist = f.get("distribution") or "Fixed"
	if dist == "Fixed":
		return nominal
	if dist == "Normal":
		return rng.gauss(nominal, f.get("sd") or 0.0)
	low, high = f.get("dist_low"), f.get("dist_high")
	if low is None or high is None:
		low, high = f["low"], f["high"]
	if dist == "Uniform":
		return rng.uniform(low, high)
	if dist == "Triangular":
		return rng.triangular(low, high, min(max(nominal, low), high))
	raise ValueError(f"unknown distribution {dist!r}")


def _limits_ok(value: float, r: dict) -> bool:
	limits = r.get("limits") or "None"
	if limits in ("Lower and Upper", "Lower Only") and value < r["lower"]:
		return False
	if limits in ("Lower and Upper", "Upper Only") and value > r["upper"]:
		return False
	return True


def _ppk(m: float, s: float, r: dict) -> float | None:
	limits = r.get("limits") or "None"
	if s <= 0 or limits == "None":
		return None
	sides = []
	if limits in ("Lower and Upper", "Lower Only"):
		sides.append((m - r["lower"]) / (3 * s))
	if limits in ("Lower and Upper", "Upper Only"):
		sides.append((r["upper"] - m) / (3 * s))
	return min(sides)


def what_if(
	factors: list[dict],
	responses: list[dict],
	models: dict[str, dict],
	*,
	iterations: int = 2000,
	seed: int | None = None,
	include_model_error: bool = True,
) -> dict:
	"""Monte Carlo of the fitted models. `factors`: name, low, high, nominal, distribution, sd,
	dist_low, dist_high (actual units). `responses`: name, limits, lower, upper. `models`: the fit
	for each response name."""
	if not 1 <= iterations <= MAX_ITERATIONS:
		raise ValueError(f"iterations must be between 1 and {MAX_ITERATIONS}")
	rng = random.Random(seed)
	modelled = [r for r in responses if r["name"] in models]
	if not modelled:
		raise ValueError("no response has a fitted model; fit the models first")
	samples: dict[str, list[float]] = {r["name"]: [] for r in modelled}
	all_ok = 0
	outside_range = 0
	for _ in range(iterations):
		values = [_draw(rng, f) for f in factors]
		if any(v < f["low"] or v > f["high"] for v, f in zip(values, factors, strict=True)):
			outside_range += 1
		point = [coded(v, f["low"], f["high"]) for v, f in zip(values, factors, strict=True)]
		ok = True
		for r in modelled:
			m = models[r["name"]]
			y = predict(m, point)
			if include_model_error and m.get("rmse"):
				y += rng.gauss(0.0, m["rmse"])
			samples[r["name"]].append(y)
			ok = ok and _limits_ok(y, r)
		all_ok += ok
	results = []
	for r in modelled:
		ys = samples[r["name"]]
		m, s = stats.mean(ys), stats.stdev(ys)
		results.append(
			{
				"response": r["name"],
				"mean": m,
				"sd": s,
				"p05": stats.percentile(ys, 5),
				"p50": stats.percentile(ys, 50),
				"p95": stats.percentile(ys, 95),
				"probability_in_limits": sum(_limits_ok(y, r) for y in ys) / len(ys),
				"predicted_ppk": _ppk(m, s, r),
			}
		)
	return {
		"iterations": iterations,
		"seed": seed,
		"include_model_error": include_model_error,
		"probability_all_in_limits": all_ok / iterations,
		"percent_draws_outside_studied_range": 100.0 * outside_range / iterations,
		"responses": results,
	}


def design_space(
	factors: list[dict],
	responses: list[dict],
	models: dict[str, dict],
	x_factor: int,
	y_factor: int,
	steps: int = 21,
) -> dict:
	"""Grid over two factors (indices into `factors`), the others at nominal. A point is inside when
	every modelled response with limits predicts within them."""
	if x_factor == y_factor:
		raise ValueError("choose two different factors")
	if not 3 <= steps <= 101:
		raise ValueError("steps must be between 3 and 101")
	modelled = [r for r in responses if r["name"] in models and (r.get("limits") or "None") != "None"]
	if not modelled:
		raise ValueError("no response with limits has a fitted model")
	base = [coded(f["nominal"], f["low"], f["high"]) for f in factors]
	fx, fy = factors[x_factor], factors[y_factor]
	xs = [fx["low"] + (fx["high"] - fx["low"]) * i / (steps - 1) for i in range(steps)]
	ys = [fy["low"] + (fy["high"] - fy["low"]) * i / (steps - 1) for i in range(steps)]
	grid, inside = [], 0
	for yv in ys:
		row = []
		for xv in xs:
			point = list(base)
			point[x_factor] = coded(xv, fx["low"], fx["high"])
			point[y_factor] = coded(yv, fy["low"], fy["high"])
			ok = all(_limits_ok(predict(models[r["name"]], point), r) for r in modelled)
			inside += ok
			row.append(1 if ok else 0)
		grid.append(row)
	return {
		"x_factor": fx["name"],
		"y_factor": fy["name"],
		"x_values": xs,
		"y_values": ys,
		"grid": grid,
		"percent_inside": 100.0 * inside / (steps * steps),
		"held_at_nominal": {
			f["name"]: f["nominal"] for i, f in enumerate(factors) if i not in (x_factor, y_factor)
		},
		"responses": [r["name"] for r in modelled],
	}
