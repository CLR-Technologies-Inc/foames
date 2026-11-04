# Case study: changeover and micro-stop reduction on a discrete line

| | |
| --- | --- |
| Status | Scaffold |
| Data | Illustrative (replace with measured data) |
| Segment | Discrete |
| Plant | Plant A (anonymised) |

## 1. Summary

TODO after results: line, change, change in OEE and first-pass yield.

## 2. Context

TODO: product family, shifts per day, parts per shift, and the constraint (typically the line is the bottleneck and OEE is the cheapest capacity).

Connection: CNC and PLC data reach FoaMES through the signed webhook or an OPC UA or Sparkplug B gateway (see [machine-data.md](../machine-data.md) and [ignition.md](../ignition.md)). Work orders and items are referenced through the ERP adapter as External References, never as links.

## 3. The improvement

Candidate changes to study, pick one per study so the effect can be attributed:

- Single-minute exchange of die (SMED) on the changeover with the largest Setup minutes.
- Micro-stop elimination on the machine with the most short Down intervals.
- Preventive maintenance moved from calendar to run hours or counts ([maintenance.md](../maintenance.md)).
- Andon response targets tightened ([andon.md](../andon.md)).

## 4. Measurement design

| Metric | FoaMES source | Definition |
| --- | --- | --- |
| OEE, availability, performance, quality | OEE Period, `get_oee` | [oee.md](../oee.md) |
| Setup minutes per changeover | Machine Event states, Downtime Pareto | Time in Setup between the last good part of order A and the first of order B |
| Micro-stop count | Downtime Record, Process Throughput | Down intervals shorter than the site's threshold (state it) |
| First-pass yield | good and scrap counters | Good divided by good plus scrap |
| MTBF, MTTR | MTBF and MTTR report | |
| Control of the critical dimension | SPC Control Chart ([spc.md](../spc.md)) | I-MR or X-bar R with run-rule signals |

TODO: fill machines, Source IDs, ideal cycle time per machine (it sets performance, so say how it was derived).

## 5. Data connection

TODO: gateway, event rate, gaps. Counters are sent as running totals; a restart yields zero for the first reading, which is expected.

## 6. Results

TODO: table from the template. Show the Downtime Pareto before and after.

## 7. What else changed

TODO: product mix and order sizes change the number of changeovers; normalise per changeover.

## 8. Gaps

TODO.

## 9. Lessons and next steps

TODO.
