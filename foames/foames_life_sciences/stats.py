# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Small statistics for the life-sciences module: Student's t distribution, summaries, and a dense
linear solver. Standard library only, no Frappe.

The t distribution goes through the regularized incomplete beta function, evaluated with the
continued fraction of Numerical Recipes (Press et al., 3rd ed., section 6.4); the quantile is found
by bisection on the CDF, which is accurate to well below the precision a comparability or
regression report prints.
"""

from __future__ import annotations

import math


def mean(values: list[float]) -> float:
	if not values:
		raise ValueError("mean of no values")
	return sum(values) / len(values)


def stdev(values: list[float]) -> float:
	"""Sample standard deviation (n - 1 denominator); 0 for fewer than two values."""
	n = len(values)
	if n < 2:
		return 0.0
	m = mean(values)
	return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def percentile(values: list[float], q: float) -> float:
	"""Linear-interpolated percentile, q in [0, 100]."""
	if not values:
		raise ValueError("percentile of no values")
	ordered = sorted(values)
	if len(ordered) == 1:
		return ordered[0]
	pos = (len(ordered) - 1) * q / 100.0
	low = math.floor(pos)
	high = min(low + 1, len(ordered) - 1)
	return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _betacf(a: float, b: float, x: float) -> float:
	tiny = 1e-300
	qab, qap, qam = a + b, a + 1.0, a - 1.0
	c, d = 1.0, 1.0 - qab * x / qap
	d = 1.0 / (d if abs(d) > tiny else tiny)
	h = d
	for m in range(1, 300):
		m2 = 2 * m
		aa = m * (b - m) * x / ((qam + m2) * (a + m2))
		d = 1.0 + aa * d
		d = 1.0 / (d if abs(d) > tiny else tiny)
		c = 1.0 + aa / c
		c = c if abs(c) > tiny else tiny
		h *= d * c
		aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
		d = 1.0 + aa * d
		d = 1.0 / (d if abs(d) > tiny else tiny)
		c = 1.0 + aa / c
		c = c if abs(c) > tiny else tiny
		delta = d * c
		h *= delta
		if abs(delta - 1.0) < 1e-14:
			break
	return h


def betainc(a: float, b: float, x: float) -> float:
	"""Regularized incomplete beta I_x(a, b)."""
	if x <= 0.0:
		return 0.0
	if x >= 1.0:
		return 1.0
	ln = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
	front = math.exp(ln)
	if x < (a + 1.0) / (a + b + 2.0):
		return front * _betacf(a, b, x) / a
	return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
	"""P(T <= t) for Student's t with df degrees of freedom (df may be fractional, as with Welch)."""
	if df <= 0:
		raise ValueError("degrees of freedom must be positive")
	x = df / (df + t * t)
	tail = 0.5 * betainc(df / 2.0, 0.5, x)
	return 1.0 - tail if t >= 0 else tail


def t_ppf(p: float, df: float) -> float:
	"""The t value with P(T <= t) = p."""
	if not 0.0 < p < 1.0:
		raise ValueError("p must be between 0 and 1")
	if p == 0.5:  # NOSONAR -- exact midpoint: nearby p must still reach the quantile solver
		return 0.0
	low, high = -1.0, 1.0
	while t_cdf(low, df) > p:
		low *= 2.0
	while t_cdf(high, df) < p:
		high *= 2.0
	for _ in range(200):
		mid = (low + high) / 2.0
		if t_cdf(mid, df) < p:
			low = mid
		else:
			high = mid
		if high - low < 1e-12:
			break
	return (low + high) / 2.0


def two_sided_p(t: float, df: float) -> float:
	return 2.0 * (1.0 - t_cdf(abs(t), df))


def solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
	"""Solve A x = b by Gaussian elimination with partial pivoting. Raises ValueError when A is
	singular (a design that cannot estimate the model)."""
	n = len(matrix)
	a = [[*row, rhs[i]] for i, row in enumerate(matrix)]
	for col in range(n):
		pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
		scale = max(abs(v) for v in a[pivot][:n]) or 1.0
		if abs(a[pivot][col]) < 1e-10 * scale:
			raise ValueError("singular matrix")
		a[col], a[pivot] = a[pivot], a[col]
		for r in range(col + 1, n):
			f = a[r][col] / a[col][col]
			if f:
				for c in range(col, n + 1):
					a[r][c] -= f * a[col][c]
	x = [0.0] * n
	for r in range(n - 1, -1, -1):
		x[r] = (a[r][n] - sum(a[r][c] * x[c] for c in range(r + 1, n))) / a[r][r]
	return x


def inverse(matrix: list[list[float]]) -> list[list[float]]:
	n = len(matrix)
	columns = [solve(matrix, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
	return [[columns[j][i] for j in range(n)] for i in range(n)]
