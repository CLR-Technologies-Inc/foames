# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Scale-up correlations for stirred, aerated vessels (bioreactors, fermenters, crystallizers and
reactors). Standard library only, no Frappe.

Geometric similarity is assumed: every length scales with the cube root of the volume ratio. For
each common criterion the receiving-scale impeller speed is computed, and with it what the other
criteria become, so the trade-off is visible (holding P/V raises tip speed; holding tip speed
drops P/V; holding Re is almost never practical):

- power P = Np rho N^3 D^5 (turbulent regime, constant power number Np);
- Reynolds number Re = rho N D^2 / mu; tip speed v_tip = pi N D;
- constant P/V: N2 = N1 (D1/D2)^(2/3); constant tip speed: N2 = N1 (D1/D2);
  constant Re: N2 = N1 (D1/D2)^2; constant mixing time (turbulent): N2 = N1;
- aeration: vvm = Q / V; superficial gas velocity vs = Q / (pi T^2 / 4);
- kLa = a (P/V)^alpha vs^beta, by default van 't Riet (1979): a = 0.026, alpha = 0.4, beta = 0.5
  for coalescing (water-like) broths and a = 0.002, alpha = 0.7, beta = 0.2 for non-coalescing
  (salt) solutions, P/V in W/m^3, vs in m/s, kLa in 1/s. Gassed power is not corrected; enter the
  gassed power number if it is known.

Units: volumes in litres, lengths in metres, speed in rpm, density in kg/m^3, viscosity in Pa s,
gas flow in L/min. Results are estimates for engineering judgment, not a validated scale-up.
"""

from __future__ import annotations

import math

CRITERIA = ("Constant P/V", "Constant Tip Speed", "Constant Reynolds", "Constant Mixing Time")
KLA_CORRELATIONS = {
	"Coalescing (van 't Riet)": (0.026, 0.4, 0.5),
	"Non-coalescing (van 't Riet)": (0.002, 0.7, 0.2),
}


def _positive(name: str, value: float | None) -> float:
	if value is None or value <= 0:
		raise ValueError(f"{name} must be positive")
	return float(value)


def state(
	volume_l: float,
	impeller_d: float,
	rpm: float,
	np_: float,
	rho: float,
	mu: float,
	tank_d: float | None = None,
	gas_lpm: float | None = None,
	kla: tuple[float, float, float] | None = None,
) -> dict:
	n = rpm / 60.0
	v = volume_l / 1000.0
	power = np_ * rho * n**3 * impeller_d**5
	out = {
		"volume_l": volume_l,
		"impeller_diameter_m": impeller_d,
		"tank_diameter_m": tank_d,
		"rpm": rpm,
		"power_w": power,
		"p_per_v_w_m3": power / v,
		"tip_speed_m_s": math.pi * n * impeller_d,
		"reynolds": rho * n * impeller_d**2 / mu,
		"gas_l_min": gas_lpm,
		"vvm": None,
		"superficial_velocity_m_s": None,
		"kla_per_h": None,
	}
	if gas_lpm is not None and gas_lpm > 0:
		out["vvm"] = gas_lpm / volume_l
		if tank_d:
			vs = (gas_lpm / 1000.0 / 60.0) / (math.pi * tank_d**2 / 4.0)
			out["superficial_velocity_m_s"] = vs
			if kla:
				a, alpha, beta = kla
				out["kla_per_h"] = a * out["p_per_v_w_m3"] ** alpha * vs**beta * 3600.0
	return out


def scale_up(
	*,
	small_volume_l: float,
	large_volume_l: float,
	impeller_diameter_m: float,
	rpm: float,
	power_number: float = 5.0,
	density: float = 1000.0,
	viscosity: float = 0.001,
	tank_diameter_m: float | None = None,
	gas_l_min: float | None = None,
	gas_rule: str = "Constant vvm",
	kla_correlation: str = "Coalescing (van 't Riet)",
	kla_coefficients: tuple[float, float, float] | None = None,
) -> dict:
	"""The small-scale state and, for each criterion, the large-scale state under geometric
	similarity. Gas flow at the large scale follows `gas_rule`: Constant vvm or Constant
	Superficial Gas Velocity."""
	v1 = _positive("small volume", small_volume_l)
	v2 = _positive("large volume", large_volume_l)
	d1 = _positive("impeller diameter", impeller_diameter_m)
	rpm1 = _positive("impeller speed", rpm)
	np_ = _positive("power number", power_number)
	rho = _positive("density", density)
	mu = _positive("viscosity", viscosity)
	if tank_diameter_m is not None:
		_positive("tank diameter", tank_diameter_m)
	if gas_rule not in ("Constant vvm", "Constant Superficial Gas Velocity"):
		raise ValueError("gas rule must be Constant vvm or Constant Superficial Gas Velocity")
	kla = kla_coefficients or KLA_CORRELATIONS.get(kla_correlation)
	if kla is None:
		raise ValueError(f"unknown kLa correlation {kla_correlation!r}")
	length_ratio = (v2 / v1) ** (1.0 / 3.0)
	d2 = d1 * length_ratio
	t1 = tank_diameter_m
	t2 = t1 * length_ratio if t1 else None
	gas2 = None
	if gas_l_min:
		gas2 = gas_l_min * (v2 / v1) if gas_rule == "Constant vvm" else gas_l_min * length_ratio**2
	small = state(v1, d1, rpm1, np_, rho, mu, t1, gas_l_min, kla)
	speeds = {
		"Constant P/V": rpm1 * (d1 / d2) ** (2.0 / 3.0),
		"Constant Tip Speed": rpm1 * (d1 / d2),
		"Constant Reynolds": rpm1 * (d1 / d2) ** 2,
		"Constant Mixing Time": rpm1,
	}
	large = []
	for criterion in CRITERIA:
		s = state(v2, d2, speeds[criterion], np_, rho, mu, t2, gas2, kla)
		s["criterion"] = criterion
		s["ratios"] = {
			key: (s[key] / small[key]) if small.get(key) and s.get(key) is not None else None
			for key in ("rpm", "power_w", "p_per_v_w_m3", "tip_speed_m_s", "reynolds", "kla_per_h")
		}
		large.append(s)
	return {
		"volume_ratio": v2 / v1,
		"length_ratio": length_ratio,
		"surface_to_volume_ratio": 1.0 / length_ratio,
		"gas_rule": gas_rule if gas_l_min else None,
		"kla_coefficients": list(kla),
		"small": small,
		"large": large,
		"notes": [
			"Geometric similarity assumed; lengths scale with the cube root of the volume ratio.",
			"Jacket area per volume falls with the length ratio; check heat removal at the large scale.",
			"Turbulent regime assumed for a constant power number; check Re > 10,000 at both scales.",
		],
	}
