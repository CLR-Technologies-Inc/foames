"""An independent EWMA computation the hidden tests compare against."""

import itertools
import math
import statistics


def d2_2():
	return 2 / math.sqrt(math.pi)  # expected range of two standard normals: 1.128379...


def expected(values, lam, L, baseline=None):
	values = [float(v) for v in values]
	base = values[: baseline or len(values)]
	cl = statistics.fmean(base)
	sigma = statistics.fmean(abs(b - a) for a, b in itertools.pairwise(base)) / d2_2()
	z, zs, ucl, lcl, sig = cl, [], [], [], []
	for i, x in enumerate(values, start=1):
		z = lam * x + (1 - lam) * z
		w = L * sigma * math.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * i)))
		zs.append(z)
		ucl.append(cl + w)
		lcl.append(cl - w)
		if z > cl + w or z < cl - w:
			sig.append(i - 1)
	return {"points": zs, "cl": cl, "ucl": ucl, "lcl": lcl, "signals": sig, "sigma": sigma}
