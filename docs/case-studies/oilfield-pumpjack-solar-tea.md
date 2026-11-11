# White paper: techno-economic analysis of standard and solar-supported pumpjacks

| | |
| --- | --- |
| Status | Draft |
| Data | **Illustrative.** Every input is a stated assumption, none is measured or sourced. Do not quote the results as findings. |
| Segment | Process (artificial lift, one well as one `Machine`) |
| Plant | Well A (anonymised) |
| Period | Model year of 8,760 hours, 20-year project life |
| Model | [pumpjack_tea.py](pumpjack_tea.py), standard library only. `python docs/case-studies/pumpjack_tea.py` reproduces every table below |

## 1. Summary

A beam pumpjack is a near-constant electrical load. At the assumed well (60 bbl/day gross fluid, 1,200 m net lift, 30% system efficiency) it draws about 3.7 kW on average, 32,400 kWh a year. This paper compares that standard, grid-fed unit with units supported by a behind-the-meter solar array, with and without a battery.

On the assumptions in section 4, and **with the grid as the backup**:

- A small array (4 kWp) covers about 23% of the energy and saves about USD 680 a year in year one, but its net present cost over 20 years (USD 38.7k) is slightly above grid-only (USD 36.8k). It is a break-even, not a win.
- A battery adds cost and no saving. The array never exceeds the load, so there is no surplus to store. A battery only pays when it buys something else: ride-through, or running without a grid connection.
- The result is decided by three inputs, in this order: the cost of **not** extending a power line (a USD 25,000 avoided line extension turns scenario C into a USD 7.5k net saving), the grid price, and the installed cost per kWp.
- Raising the lift system's efficiency from 30% to 50% cuts the grid-only cost by 40%, more than any solar option does. Solar is a supply-side measure; efficiency is the cheaper first step.

The decision rule that follows: solar supported pumping is worth pricing where a line extension is avoided or the grid price is high, and it should follow a lift-efficiency review, not replace it.

## 2. Context

Beam pumpjacks lift fluid from a large share of onshore wells, and are often at the end of long, lightly loaded distribution lines. Electricity for lifting is a recurring operating cost; remote leases may instead run gas engines, which this paper does not model. The questions an operator asks are how much energy a unit uses, what it costs per barrel, and whether solar changes either. FoaMES can answer the measured half of those questions once the well is connected (section 7).

## 3. The options compared

| Scenario | Description |
| --- | --- |
| A. Standard | Grid-fed motor and unit, no solar. The baseline |
| B. Grid + 2 kWp PV | Small behind-the-meter array, no storage, no export credit |
| C. Grid + 4 kWp PV | Array sized near the average load |
| D. C + 10 kWh battery | Adds storage to C |
| E. Grid + 8 kWp PV + 40 kWh battery | Oversized array with storage, to show the effect of surplus |

Not modelled: an off-grid system, a gas engine, a variable speed drive, or a pump-off controller. These are separate options and several are likely better than solar alone; see section 6.

## 4. Method and assumptions

**Load.** Hydraulic power is `rho * g * Q * H`: 900 kg/m3, 60 bbl/day (1.10e-4 m3/s), 1,200 m of net lift, giving 1.17 kW. Electrical load is hydraulic power divided by system efficiency (30%) and multiplied by the running fraction (95%): **3.70 kW average, 32,449 kWh/year.** The load is treated as constant; stroke-by-stroke fluctuation and regeneration are ignored.

**Solar.** A clear-sky half-sine profile with a seasonal day length, scaled to 1,900 kWh per kWp a year, and 0.5% degradation a year. No cloud variability, so the model slightly overstates how well output matches load on poor days.

**Dispatch.** Hourly: the array serves the load first, surplus charges the battery (90% round trip), and the grid covers the remainder. Export is credited at USD 0.

**Economics.** Discount rate 8%, 20 years, grid price USD 0.10/kWh rising 2% a year, PV USD 1,600/kWp installed plus USD 3,000 for the inverter, protection and metering, USD 20/kWp-year O&M, battery USD 450/kWh with a 10-year life and a 1% a year O&M. Emissions at 0.39 kg CO2 per kWh grid. All of these are placeholders.

**Net present cost** is capex plus discounted operating cost over the life, with the battery replaced at year 10. **LCOE** here is that cost over discounted energy delivered to the well. **Simple payback** is extra capex over year-one operating saving.

## 5. Results

| Scenario | Capex USD | PV used kWh | Grid kWh | Solar share | Year-1 opex USD | Net present cost USD | LCOE USD/kWh | CO2 t over life | Simple payback yr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. Standard | 0 | 0 | 32,449 | 0% | 3,245 | 36,840 | 0.116 | 253 | n/a |
| B. 2 kWp PV | 6,200 | 3,800 | 28,649 | 12% | 2,905 | 39,279 | 0.123 | 225 | 18.2 |
| C. 4 kWp PV | 9,400 | 7,600 | 24,849 | 23% | 2,565 | 38,718 | 0.122 | 197 | 13.8 |
| D. C + 10 kWh battery | 13,900 | 7,600 | 24,849 | 23% | 2,610 | 45,744 | 0.144 | 197 | 21.9 |
| E. 8 kWp PV + 40 kWh battery | 33,800 | 14,919 | 17,530 | 46% | 2,093 | 66,007 | 0.207 | 142 | 29.3 |

Reading the table:

- Solar share rises with array size, but net present cost does not fall. Each kWp costs more up front than the discounted grid energy it displaces at these prices.
- D equals C in energy and costs more. The battery is idle because PV output stays below the 3.7 kW load every hour.
- E reaches 46% only by adding storage that captures a small surplus at midday; the extra capex is not repaid.
- Emissions fall in proportion to PV energy used (about 56 t over 20 years for C), but at these prices that is carbon avoided at a net cost, not a saving.

### Sensitivity, scenario A against C

A positive value means solar C has the lower net present cost.

| Case | A USD | C USD | A minus C USD |
| --- | --- | --- | --- |
| Grid price 0.06 | 22,104 | 27,305 | -5,201 |
| Grid price 0.10 (base) | 36,840 | 38,718 | -1,878 |
| Grid price 0.16 | 58,944 | 55,837 | 3,107 |
| PV cost 1,100 /kWp | 36,840 | 36,718 | 122 |
| PV cost 2,200 /kWp | 36,840 | 41,118 | -4,278 |
| PV yield 1,500 kWh/kWp | 36,840 | 40,467 | -3,627 |
| PV yield 2,100 kWh/kWp | 36,840 | 37,843 | -1,003 |
| Discount rate 12% | 27,450 | 31,224 | -3,774 |
| Line extension avoided 25,000 | 36,840 | 29,318 | 7,522 |
| System efficiency 40% | 27,630 | 29,692 | -2,062 |
| System efficiency 50% | 22,104 | 24,797 | -2,693 |

Solar needs a grid price near USD 0.14 or an installed cost near USD 1,100/kWp to break even on energy savings alone. An avoided line extension or similar connection cost overturns the result at once. A higher discount rate hurts solar because its cost is up front.

## 6. Discussion and limits

- **Efficiency first.** A 50% efficient system lowers grid-only cost from USD 36.8k to 22.1k net present cost, a larger gain than any solar case. Pump-off control, a correctly sized motor and counterbalance, and a variable speed drive are the first things to price. Solar on top of an efficient unit is also cheaper, since it is smaller.
- **Demand charges and time-of-use rates** are not modelled; a solar array that lowers a billed peak would improve the result.
- **Reliability and safety.** Solar-supported units in this model remain grid-connected, so downtime behaviour is unchanged. Off-grid configurations change the availability argument and need their own analysis, including generator or battery ride-through.
- **Single well, one set of assumptions.** The result does not generalise to other depths, rates or tariffs. Run the model with site values.
- **Methodological simplifications.** Constant load, clear-sky solar, no cloud variability, first-order degradation scaling of year-one dispatch, no tax, incentive, depreciation or salvage value. Each can move the result, and incentives could move it a lot.

## 7. Measuring it in FoaMES

The model is a prediction. FoaMES can replace its load and generation inputs with measurements, so the TEA is rerun on real figures.

| Concept | FoaMES representation |
| --- | --- |
| Well and pumpjack | One `Machine`, Source ID from the SCADA or controller |
| Pumping | State Running; pump-off or idle wait as Idle; fault as Down with a Downtime Reason |
| Loss of controller signal | Unknown (staleness check), counted as loss, as always |
| Grid energy | Counter `energy_grid_kwh`, running total from the meter |
| Barrels lifted | Counter `good` as a running total of produced fluid or oil, whichever the study states |
| PV generation | Counter `pv_kwh` (see the gap below) |
| Polished-rod load, motor current, tank level | Measurement events, charted with the SPC Control Chart |

Metrics, with the FoaMES source for each:

| Metric | Source | Definition |
| --- | --- | --- |
| Specific energy, kWh per bbl | `foames.foames_mes.kpi.resource_intensity` | Grid kWh delta over barrels delta, for the same window |
| Run time and availability | OEE Period, `get_oee` | Same ledger before and after; Unknown stays loss |
| Solar share | Counters | `pv_kwh` delta over (`pv_kwh` + `energy_grid_kwh`) delta, assuming all PV is self-consumed |
| Downtime by reason | Downtime Pareto | Outages, including any caused by the solar or inverter equipment |

Baseline: at least 4 weeks of the standard unit in a comparable season, then the same wells after the array is in. Pair wells at similar depth and rate, or compare one well before and after and name the confounders (section 8).

### Gaps in FoaMES for this study

- **PV generation is not a consumed input.** FoaMES treats counters named `energy`, `kwh`, `electricity` and similar (exactly or with `_unit`) as consumption, so a counter called `energy_pv_kwh` would be added to grid energy and double-count. Use a name outside that list, such as `pv_kwh`, and compute site energy and solar share in the study. A generation counter type, and a net-energy figure that nets it, would be a change for the kernel.
- **No tariff or cost data in FoaMES.** Prices and the capex come from finance or the ERP; list their source in the study.
- **No export counter.** Surplus export is not recorded; confirm the array never exports, or meter it separately.
- Gaps become issues.

## 8. What else could change the result

Well decline (falling rate changes the load and the barrel denominator), seasonal weather, workovers, pump or motor changes during the study, a tariff change, and grid outages that the array does not ride through. Each could bias a before-and-after comparison; state which way.

## 9. Next steps

1. Replace every assumption in section 4 with site data, and cite the source of each in the model call. Vendor quotes are claims and must be labelled as such.
2. Price the efficiency options (pump-off control, variable speed drive, motor and counterbalance) in the same model so the comparison is complete.
3. Add the off-grid and gas-engine cases and a demand-charge term if the site tariff has one.
4. Connect one well to FoaMES, measure 4 weeks of baseline, and rerun with measured load.

## Sources

No external figures are used. All inputs are assumptions made for illustration, set as defaults in [pumpjack_tea.py](pumpjack_tea.py). Before publication, each must be replaced by a measured value or a cited public source.
