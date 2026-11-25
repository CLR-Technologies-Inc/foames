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

"""An independent EWMA computation the hidden tests compare against."""

import itertools
import math
import statistics


def d2_2():
	return 2 / math.sqrt(math.pi)  # expected range of two standard normals: 1.128379...


def expected(values, lam, L, baseline=None):
	values = [float(v) for v in values]
	base = values if baseline is None else values[:baseline]
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
