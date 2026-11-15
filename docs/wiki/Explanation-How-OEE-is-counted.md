OEE (availability × performance × quality) is easy to define and easy to fake. The usual ways a plant's OEE drifts from the truth are well known: a machine that stopped reporting is assumed to have kept running, a counter reset is booked as a huge burst of production, and any unexplained stop is quietly filed as "planned". FoaMES is built so that none of these can happen by default.

## Every minute lands in exactly one bucket

FoaMES builds a **time ledger** for the planned period from the machine's own state history, with every Downtime Record laid over it. Each minute is Run, Planned downtime, Unplanned downtime, Idle, Setup or Unknown. Nothing is typed in: there is no field where someone can enter a run time.

Because the ledger is exhaustive, the parts always add up to the planned time, and you can always ask *where did the minutes go?* and get an answer.

## Silence is loss, never run time

If a machine stops reporting, FoaMES does not assume it kept doing what it last said. After **Mark Machine Unknown After** (15 minutes by default) the scheduler writes an Unknown state, and those minutes count as loss. The Sparkplug B gateway does it immediately when a node or device dies.

This makes OEE look worse when the data path is broken, which is the point. A low **Signal Coverage** on an OEE Period tells you the number is low because the machine was silent, not necessarily because it was stopped. Fix the gateway first, then act on the number.

## Counters become deltas

Machines report running totals. FoaMES stores the difference from the previous reading on each Count event and sums those deltas. A first reading only sets the baseline. A reset counts zero. A reading that arrives after a later one counts zero. A configured rollover is counted as production. FoaMES never invents production, and never subtracts one counter from another on your behalf: if a total includes rejects, derive good on the gateway.

## Only a person makes a stop planned

A Downtime Record opens automatically when a machine goes Down. Until someone assigns a reason, it is unplanned loss. Only a reason marked **Counts As Planned Downtime** removes the minutes from the availability base. A stop nobody explained cannot improve your OEE.

## Lines are rolled up, not averaged

A line's OEE in the OEE Trend report is built from the summed ledgers and counts of its machines, weighted by time, never an average of percentages. A short trial run on one machine cannot move the line as much as a full shift on another. Whether that roll-up or the bottleneck machine is "the line's OEE" is left to the plant.

## Performance is capped and flagged

If a machine produced more than its ideal cycle time allows, performance is capped at 100 % and a note says so. The usual causes are an ideal cycle time that is too long or a counter that double counts, and both are worth fixing rather than hiding.

The arithmetic is in `foames/foames_mes/oee.py`, which has no Frappe dependency and can be read and tested on its own. A full worked example is in [docs/oee.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/oee.md#a-worked-example), and [Tutorial 2](Tutorial-2-Your-first-machine-and-OEE) lets you watch the ledger work.
