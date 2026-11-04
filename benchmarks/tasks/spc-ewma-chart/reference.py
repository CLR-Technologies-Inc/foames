"""Reference solution for spc-ewma-chart."""

from pathlib import Path

CODE = '''

def ewma_chart(values, lam: float = 0.2, L: float = 3.0, baseline: int | None = None) -> dict:
	"""Exponentially weighted moving average chart with exact time-varying limits. The centre line and
	sigma come from the first `baseline` values (all of them when None), sigma from the average
	moving range as in imr_chart. Small sustained shifts show up here long before they cross the
	3-sigma limits of an individuals chart."""
	if not 0 < lam <= 1:
		raise ValueError("lambda must be in (0, 1]")
	if L <= 0:
		raise ValueError("L must be above zero")
	values = [float(v) for v in values]
	base = values[: baseline or len(values)]
	if len(base) < 2:
		raise ValueError("an EWMA chart needs at least two baseline values")
	cl = statistics.fmean(base)
	sigma = statistics.fmean(abs(b - a) for a, b in pairwise(base)) / factors(2)["d2"]
	points, ucl, lcl, signals = [], [], [], []
	z = cl
	for i, x in enumerate(values, start=1):
		z = lam * x + (1 - lam) * z
		width = L * sigma * math.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * i)))
		points.append(z)
		ucl.append(cl + width)
		lcl.append(cl - width)
		if z > cl + width or z < cl - width:
			signals.append(
				{"index": i - 1, "rule": "EWMA", "name": "Beyond EWMA limit", "description": "the EWMA left its control limits"}
			)
	return {
		"chart": "EWMA",
		"points": points,
		"cl": cl,
		"ucl": ucl,
		"lcl": lcl,
		"signals": signals,
		"sigma_within": sigma,
		"lambda": lam,
		"L": L,
		"baseline_points": len(base),
	}
'''

TEST = """import unittest

from foames.foames_mes.spc import ewma_chart


class TestEWMA(unittest.TestCase):
	def test_small_shift_signals(self):
		values = [10.0, 10.2, 9.9, 10.1, 9.8, 10.0, 10.1, 9.9] * 4 + [10.3] * 20
		chart = ewma_chart(values, baseline=32)
		self.assertTrue(chart["signals"])
		self.assertGreaterEqual(chart["signals"][0]["index"], 32)

	def test_rejects_bad_lambda(self):
		with self.assertRaises(ValueError):
			ewma_chart([1, 2, 3], lam=0)
"""


def apply(workspace: Path):
	path = workspace / "foames" / "foames_mes" / "spc.py"
	path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + CODE, encoding="utf-8")
	(workspace / "foames" / "foames_mes" / "test_spc_ewma.py").write_text(TEST, encoding="utf-8")
	(workspace / "BENCH_NOTES.md").write_text(
		"Reference solution. ewma_chart estimates the centre line and sigma from the baseline only, as "
		"imr_chart does, and judges every point against exact time-varying limits. With lambda 0.2 and "
		"L 3 the in-control average run length is about 500 points, so roughly one false alarm per 500 "
		"parts should be expected; tune L for the plant's tolerance. The chart says a shift happened, not "
		"why: the nozzle-wear cause has to be confirmed by a person.\n",
		encoding="utf-8",
	)
