# Case study: autonomous trucks in yard and line-haul logistics

| | |
| --- | --- |
| Status | Scaffold |
| Data | Illustrative (replace with measured data) |
| Segment | Operational and logistics |
| Plant | Plant A (anonymised) |

## 1. Summary

TODO after results: scope, change, loads moved, intervention rate, availability, dwell time.

## 2. Context

TODO: choose one scope, because the risks differ.

| Scope | What it means | Main risk to measure |
| --- | --- | --- |
| Autonomous yard trucks | Fixed routes inside a private site | Stops for exceptions, remote-operator interventions |
| Autonomous shuttle on a closed or geofenced route | Plant to rail head, port or warehouse | Weather and geofence limits |
| Autonomous line-haul on public roads | Highway driving, with or without a safety driver | Regulatory limits, route coverage, hand-offs at terminals |

Also state the operating mode (safety driver on board, remote supervision, none), the permits in force, and the case for change (driver availability, hours of service, safety, utilisation).

## 3. The improvement

TODO: vehicles and software release, routes, hand-off points (where a human driver takes over), the dispatch rule, go-live date.

## 4. Measurement design

As with any fleet, a truck is a `Machine` and the operator's system posts events to the signed webhook ([machine-data.md](../machine-data.md)). The mapping is a proposal; confirm it with the operator.

| Concept | FoaMES representation |
| --- | --- |
| Truck, gate, dock door, hand-off point | Machine or External Reference |
| Autonomous run with a load | State Running |
| Waiting for a dock, gate or hand-off | State Idle, Downtime Reason `Waiting` |
| Minimal-risk stop, fault, remote-operator stop | State Down with a Downtime Reason per cause |
| Loss of telematics signal | Unknown (staleness check), counted as loss |
| Intervention | Andon Call (with call type `Remote operator` or `On-site`) or Downtime Record |
| Loads, km, autonomous km | Counters, running totals |

| Metric | Source | Definition |
| --- | --- | --- |
| Intervention rate | Andon Response report, Downtime Record | Interventions per 100 loads or per 1,000 km, split by cause |
| Time to resume | Andon Response report, MTBF and MTTR | Minutes from stop to moving again |
| Availability | OEE Period, `get_oee` | Same ledger and planned time as the manned baseline |
| Autonomy share | km counters | Autonomous km over total km |
| Dock-to-dock cycle time | Process Event Log with Event Log Sources | Gate-in, dock, load, gate-out ([process-mining.md](../process-mining.md)) |
| Cost per load | ERP adapter or finance input | Include remote supervision and support staff |

Baseline: the same lanes with a manned fleet, at least 4 weeks, comparable season and traffic.

## 5. Data connection

TODO: source system, event rate, gaps, and who owns the data. Software releases change behaviour; record the release date as an event or note so results can be split by version.

## 6. Results

TODO. Report intervention rate and availability together: low interventions with long resumes can hide a capacity loss.

## 7. What else changed

TODO: software releases, route or geofence changes, weather, traffic, staffing of the remote desk.

## 8. Gaps

- No native fleet, route or yard model.
- Safety cases, incident reports and permits are not FoaMES records; cite their system of record.
- FoaMES does not dispatch or command vehicles and does not replace the vehicle's safety system. It records and suggests; people act.

## 9. Lessons and next steps

TODO.

## Sources

TODO: cite the operator, regulator or public report for every external figure; label vendor figures as claims.
