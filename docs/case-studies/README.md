# Case studies

Scaffolds for case studies of manufacturing improvements measured with FoaMES. Each one follows [_template.md](_template.md), so studies from different plants and segments can be read side by side.

| Segment | Scaffold | Improvement it is meant to document |
| --- | --- | --- |
| Discrete | [discrete-manufacturing.md](discrete-manufacturing.md) | Changeover and micro-stop reduction on a machining or assembly line, measured as OEE and yield |
| Process | [process-manufacturing.md](process-manufacturing.md) | Yield, batch cycle time and specific energy on a batch or continuous unit, measured with totaliser counters and SPC |
| Operational and logistics | [logistics-ev-adoption.md](logistics-ev-adoption.md) | Moving a yard, shuttle or regional fleet to battery-electric trucks, measured as availability, charging loss and energy per load |
| Operational and logistics | [logistics-autonomous-trucking.md](logistics-autonomous-trucking.md) | Autonomous yard, shuttle or line-haul trucks, measured as intervention rate, time to resume, availability and dwell |
| Process | [oilfield-pumpjack-solar-tea.md](oilfield-pumpjack-solar-tea.md) | Techno-economic comparison of standard and solar-supported pumpjacks, with a runnable model ([pumpjack_tea.py](pumpjack_tea.py)), measured as specific energy and solar share |

## Rules for a study

These keep a study honest and keep it consistent with how FoaMES computes things.

1. **No invented numbers.** Every figure is either measured on the site and traceable to a FoaMES record (OEE Period, Downtime Record, Machine Event, Process Event Log), or quoted from a cited public source. A section that has no data yet says `TODO: data` and stays visibly unfinished. A vendor claim is labelled as a claim.
2. **Baseline first.** Record at least 4 weeks of the metrics before the change, with the same Shift Pattern and the same Downtime Reasons as after. Say what else changed in the period (product mix, staffing, season).
3. **Same ledger before and after.** Use `get_oee` for both windows. Unknown time stays loss in both; do not drop a window because a machine went silent in it.
4. **Counters are running totals.** Report production from stored deltas, never from a sum of events someone reconstructed by hand.
5. **FoaMES suggests, people act.** A study may show Agent Suggestions that were raised, and what the people who owned them did. It must not describe FoaMES as having changed a machine, a tag or an ERP record on its own.
6. **Name the confounders and the limits.** One plant, one period, one product family is an observation, not a result that generalises.
7. **Publishing.** Get the plant's written permission before naming it, a vendor or a person. Anonymise by default (`Plant A`).

## Choosing the unit of analysis

FoaMES records a `Machine` with state, counter and measurement events. Anything that can report those can be a Machine, so the three segments map as follows.

| Segment | Machine is | State means | Counter is | Measurement is |
| --- | --- | --- | --- | --- |
| Discrete | CNC, press, assembly cell | Running, Idle, Down, Setup | Parts count | Critical dimension |
| Process | Reactor, mixer, filler, dryer | Running, Idle, Down, Setup (cleaning in place is recorded as Setup) | Feed and product totalisers | Temperature, pH, concentration |
| Logistics | Tractor, yard truck, charger, dock door | Running (moving), Idle (waiting, or charging when it is not a loss to chase), Down (faults, and charging when it is recorded as a loss) | Loads, kWh or km odometer | Battery temperature, state of charge |

FoaMES accepts the states Running, Idle, Down, Setup and Unknown, plus a fixed set of aliases (for example `waiting`, `starved` and `blocked` map to Idle); a gateway that sends `Cleaning`, `Moving` or `Charging` has its events rejected, so map those to an accepted state first. Only a Down state opens a Downtime Record, and only a Downtime Record carries a Downtime Reason. If a segment needs a state or event type FoaMES does not have, say so in the study's "Gaps" section rather than working around it. Gaps become issues.

## Data you can use without a plant

Until a site is connected, a study can be built from a stated scenario, as long as it is labelled `Illustrative` in its header and uses no real plant name. Replace the scenario with measured data before publishing as a result.
