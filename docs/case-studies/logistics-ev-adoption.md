# Case study: battery-electric trucks in site and regional logistics

| | |
| --- | --- |
| Status | Scaffold |
| Data | Illustrative (replace with measured data) |
| Segment | Operational and logistics |
| Plant | Plant A (anonymised) |

## 1. Summary

TODO after results: fleet, change, availability, charging loss, energy per load, cost per load.

## 2. Context

TODO: what moves (inbound material, finished goods, trailers between buildings, a shuttle to a rail head or port), loads per day, duty cycle (distance, stops, idle time), and the case for change (fuel cost, emissions, incentives, site air-quality limits).

## 3. The improvement

TODO: number and type of battery-electric trucks, what they replace, charger count and power, depot or yard layout, charging rule (opportunity charging at docks, overnight, or both), go-live date. Give a source for every cost and incentive figure.

## 4. Measurement design

FoaMES has no telematics gateway. A truck or charger is registered as a `Machine`; the fleet system or telematics gateway posts events to the signed webhook ([machine-data.md](../machine-data.md)). The mapping is a proposal; confirm the states with the fleet operator.

| Concept | FoaMES representation |
| --- | --- |
| Truck, charger, dock door | Machine, one per asset, Source ID from the fleet system |
| Driving with a load | State Running |
| Waiting for a dock or a load | State Idle. Idle opens no Downtime Record, so derive waiting minutes from state history |
| Charging | State Down with Downtime Reason `Charging` when the study counts it as a loss, so it shows in the Pareto; otherwise state Idle, with minutes derived from state history. The states `Charging` and `Moving` are not accepted; send Down, Idle or Running |
| Fault | State Down with a Downtime Reason |
| Loss of telematics signal | Unknown (staleness check), counted as loss |
| Loads, kWh, km | Counters, running totals |
| State of charge, battery temperature | Measurement events |

| Metric | Source | Definition |
| --- | --- | --- |
| Availability | OEE Period, `get_oee` | Run minutes over planned minutes minus planned downtime minutes, exactly as `get_oee` computes it. Waiting and unplanned charging are loss unless the site records them as planned downtime, and the study says which |
| Charging loss | Downtime Pareto (charging recorded as Down) or state history | Minutes charging per truck per day, and queueing at chargers |
| Energy per load, per km | energy, loads, distance counters | Energy delta divided by loads or km delta |
| Range margin | Measurement events | Lowest state of charge at end of duty cycle |
| MTBF and MTTR | MTBF and MTTR report | Per truck and fleet |
| Cost per load | ERP adapter or finance input | List the cost items and who supplied them |

Baseline: the same lanes and loads on the diesel fleet, at least 4 weeks, in a comparable season (cold lowers range).

## 5. Data connection

TODO: telematics source, event rate, signal gaps. Vehicle counters can reset on restart and FoaMES yields zero for the reading after a reset, so reconcile loads and kWh totals with the fleet system for the period.

## 6. Results

TODO. Report availability and charging loss separately: a fleet can show high availability and still lose capacity at the charger.

## 7. What else changed

TODO: route changes, shift pattern, order volume, weather, tariff periods.

## 8. Gaps

- No native fleet, route or yard model; assets are Machines, locations are External References or custom records.
- No telematics gateway; the webhook carries the data.
- FoaMES does not command vehicles or chargers. A suggestion such as "move charging off peak" is raised for people to act on.

## 9. Lessons and next steps

TODO.

## Sources

TODO: cite the fleet vendor, utility or public report for every external figure; label vendor figures as claims.
