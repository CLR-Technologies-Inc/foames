"""Techno-economic model for the pumpjack energy comparison (standard grid-fed vs solar-supported).

Standard library only, no Frappe. Every default below is an ILLUSTRATIVE assumption, not a measured
or sourced figure; replace each with site data before the result is used. Run it with

    python docs/case-studies/pumpjack_tea.py            # prints the tables used in the white paper
    python docs/case-studies/pumpjack_tea.py --json     # the same results as JSON

Method: one well, an hourly synthetic year, a constant electrical load (the beam pump's average over
many strokes), a clear-sky half-sine PV profile with a seasonal factor, and a simple dispatch
(PV serves the load first, a battery stores the surplus, the grid covers the rest). Costs are
discounted over the project life with an escalating tariff and a battery replacement.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field, replace

BBL_M3 = 0.158987294928
G = 9.81


@dataclass(frozen=True)
class Well:
	fluid_bbl_per_day: float = 60.0  # gross fluid lifted
	net_lift_m: float = 1200.0  # working fluid level below surface plus tubing head, as a head
	fluid_density: float = 900.0  # kg/m3, oil and water mix
	system_efficiency: float = 0.30  # wellhead electrical to hydraulic, whole beam-pump system
	uptime: float = 0.95  # fraction of hours the unit runs (the rest is pump-off, downtime)


@dataclass(frozen=True)
class Economics:
	grid_price: float = 0.10  # USD per kWh, all-in
	grid_escalation: float = 0.02  # per year
	pv_cost_per_kw: float = 1600.0  # USD per kWp installed, ground mount, small
	pv_om_per_kw_year: float = 20.0
	pv_yield_kwh_per_kwp: float = 1900.0  # annual, site dependent
	pv_degradation: float = 0.005  # per year
	battery_cost_per_kwh: float = 450.0  # USD installed
	battery_round_trip: float = 0.90
	battery_life_years: int = 10
	battery_om_fraction: float = 0.01  # of capex per year
	export_credit: float = 0.0  # USD per kWh exported; most leases get none
	discount_rate: float = 0.08
	life_years: int = 20
	grid_co2_kg_per_kwh: float = 0.39
	# Grid-side costs a solar system can avoid or add (set to 0 when not relevant)
	grid_connection_avoided: float = 0.0  # one-off capex avoided, e.g. a line extension
	controls_cost: float = 3000.0  # PV inverter, protection and metering interface


@dataclass(frozen=True)
class Scenario:
	name: str
	pv_kwp: float = 0.0
	battery_kwh: float = 0.0


@dataclass
class Result:
	name: str
	load_kwh: float
	pv_kwh: float
	grid_kwh: float
	exported_kwh: float
	solar_fraction: float
	capex: float
	opex_year1: float
	npv_cost: float
	lcoe: float
	co2_t: float
	extra: dict = field(default_factory=dict)


def hydraulic_kw(w: Well) -> float:
	q = w.fluid_bbl_per_day * BBL_M3 / 86400.0
	return w.fluid_density * G * w.net_lift_m * q / 1000.0


def average_load_kw(w: Well) -> float:
	return hydraulic_kw(w) / w.system_efficiency * w.uptime


def pv_profile(kwp: float, annual_yield: float) -> list[float]:
	"""Hourly PV output for a year in kW, from a clear-sky half-sine with a seasonal day length."""
	raw = []
	for day in range(365):
		season = math.cos(2 * math.pi * (day - 172) / 365)  # 1 at midsummer, -1 at midwinter
		half_day = 6.0 + 1.5 * season  # hours either side of solar noon
		peak = 1.0 + 0.25 * season  # higher sun, stronger peak
		for hour in range(24):
			x = hour + 0.5 - 12.0
			raw.append(peak * math.cos(math.pi * x / (2 * half_day)) if abs(x) < half_day else 0.0)
	total = sum(raw)
	scale = kwp * annual_yield / total if total else 0.0
	return [r * scale for r in raw]


def dispatch(load_kw: float, pv: list[float], battery_kwh: float, round_trip: float):
	"""Hourly dispatch. Returns (pv_to_load, grid, exported, battery_loss) in kWh for the year."""
	soc = 0.0
	eff = math.sqrt(round_trip)
	pv_used = grid = exported = loss = 0.0
	for p in pv:
		direct = min(p, load_kw)
		surplus = p - direct
		need = load_kw - direct
		if battery_kwh > 0:
			charge = min(surplus * eff, battery_kwh - soc)
			soc += charge
			loss += surplus - charge / eff if charge else 0.0
			surplus -= charge / eff
			discharge = min(need / eff, soc)
			soc -= discharge
			direct += discharge * eff
			need -= discharge * eff
			loss += discharge * (1 - eff)
		pv_used += direct
		grid += need
		exported += max(surplus, 0.0)
	return pv_used, grid, exported, loss


def evaluate(s: Scenario, w: Well, e: Economics) -> Result:
	load = average_load_kw(w)
	annual_load = load * 8760
	pv = pv_profile(s.pv_kwp, e.pv_yield_kwh_per_kwp) if s.pv_kwp else [0.0] * 8760
	pv_used, grid, exported, _loss = dispatch(load, pv, s.battery_kwh, e.battery_round_trip)

	pv_capex = s.pv_kwp * e.pv_cost_per_kw + (e.controls_cost if s.pv_kwp else 0.0)
	bat_capex = s.battery_kwh * e.battery_cost_per_kwh
	capex = pv_capex + bat_capex - (e.grid_connection_avoided if s.pv_kwp else 0.0)
	om = s.pv_kwp * e.pv_om_per_kw_year + bat_capex * e.battery_om_fraction

	npv = max(capex, 0.0)
	pv_energy_total = 0.0
	energy_total = 0.0
	co2 = 0.0
	for year in range(1, e.life_years + 1):
		deg = (1 - e.pv_degradation) ** (year - 1)
		# PV output falls with age: rescale the year-one dispatch results, a first-order approximation
		pv_u = pv_used * deg
		grid_y = max(annual_load - pv_u, 0.0)
		exp_y = exported * deg
		price = e.grid_price * (1 + e.grid_escalation) ** (year - 1)
		cash = grid_y * price + om - exp_y * e.export_credit
		df = (1 + e.discount_rate) ** -year
		npv += cash * df
		if s.battery_kwh and year % e.battery_life_years == 0 and year < e.life_years:
			npv += bat_capex * df
		pv_energy_total += pv_u * df
		energy_total += annual_load * df
		co2 += grid_y * e.grid_co2_kg_per_kwh / 1000.0
	lcoe = npv / energy_total if energy_total else 0.0
	return Result(
		name=s.name,
		load_kwh=annual_load,
		pv_kwh=pv_used,
		grid_kwh=grid,
		exported_kwh=exported,
		solar_fraction=pv_used / annual_load if annual_load else 0.0,
		capex=capex,
		opex_year1=grid * e.grid_price + om - exported * e.export_credit,
		npv_cost=npv,
		lcoe=lcoe,
		co2_t=co2,
	)


def payback_years(base: Result, alt: Result, e: Economics) -> float | None:
	"""Simple payback: extra capex over year-one operating saving."""
	saving = base.opex_year1 - alt.opex_year1
	extra = alt.capex - base.capex
	if saving <= 0:
		return None
	return max(extra, 0.0) / saving


SCENARIOS = (
	Scenario("A. Standard, grid only"),
	Scenario("B. Grid + 2 kWp PV", pv_kwp=2.0),
	Scenario("C. Grid + 4 kWp PV", pv_kwp=4.0),
	Scenario("D. Grid + 4 kWp PV + 10 kWh battery", pv_kwp=4.0, battery_kwh=10.0),
	Scenario("E. Grid + 8 kWp PV + 40 kWh battery", pv_kwp=8.0, battery_kwh=40.0),
)


def sensitivity(w: Well, e: Economics):
	"""Net present cost of scenario C against A as one input moves, one at a time."""
	rows = []
	cases = [
		("Grid price 0.06", replace(e, grid_price=0.06)),
		("Grid price 0.10 (base)", e),
		("Grid price 0.16", replace(e, grid_price=0.16)),
		("PV cost 1,100 /kWp", replace(e, pv_cost_per_kw=1100.0)),
		("PV cost 2,200 /kWp", replace(e, pv_cost_per_kw=2200.0)),
		("PV yield 1,500 kWh/kWp", replace(e, pv_yield_kwh_per_kwp=1500.0)),
		("PV yield 2,100 kWh/kWp", replace(e, pv_yield_kwh_per_kwp=2100.0)),
		("Discount rate 12%", replace(e, discount_rate=0.12)),
		("Line extension avoided 25,000", replace(e, grid_connection_avoided=25000.0)),
	]
	a, c = SCENARIOS[0], SCENARIOS[2]
	for label, env in cases:
		ra, rc = evaluate(a, w, env), evaluate(c, w, env)
		rows.append((label, ra.npv_cost, rc.npv_cost, ra.npv_cost - rc.npv_cost))
	# Efficiency lever: the same solar array on a more efficient lift system
	for eff in (0.30, 0.40, 0.50):
		w2 = replace(w, system_efficiency=eff)
		ra, rc = evaluate(a, w2, e), evaluate(c, w2, e)
		rows.append((f"System efficiency {int(eff * 100)}%", ra.npv_cost, rc.npv_cost, ra.npv_cost - rc.npv_cost))
	return rows


def main(argv: list[str]) -> int:
	w, e = Well(), Economics()
	results = [evaluate(s, w, e) for s in SCENARIOS]
	base = results[0]
	sens = sensitivity(w, e)
	if "--json" in argv:
		print(
			json.dumps(
				{
					"hydraulic_kw": hydraulic_kw(w),
					"average_load_kw": average_load_kw(w),
					"results": [r.__dict__ | {"payback_years": payback_years(base, r, e)} for r in results],
					"sensitivity": sens,
				},
				indent=2,
			)
		)
		return 0
	print(f"Hydraulic power {hydraulic_kw(w):.2f} kW; average electrical load {average_load_kw(w):.2f} kW")
	print(f"Annual load {base.load_kwh:,.0f} kWh\n")
	hdr = "| Scenario | Capex USD | PV used kWh | Grid kWh | Exported kWh | Solar share | Year-1 opex USD | Net present cost USD | LCOE USD/kWh | CO2 t over life | Simple payback yr |"
	print(hdr)
	print("|" + " --- |" * 11)
	for r in results:
		pb = payback_years(base, r, e)
		print(
			f"| {r.name} | {r.capex:,.0f} | {r.pv_kwh:,.0f} | {r.grid_kwh:,.0f} | {r.exported_kwh:,.0f} | "
			f"{r.solar_fraction:.0%} | {r.opex_year1:,.0f} | {r.npv_cost:,.0f} | {r.lcoe:.3f} | "
			f"{r.co2_t:,.0f} | {'n/a' if pb is None else f'{pb:.1f}'} |"
		)
	print("\n| Sensitivity (A vs C) | NPC A | NPC C | A minus C (positive favours solar) |\n| --- | --- | --- | --- |")
	for label, a, c, d in sens:
		print(f"| {label} | {a:,.0f} | {c:,.0f} | {d:,.0f} |")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
