All of these are standard Frappe records that `bench migrate` installs and keeps in sync. Copy and change them in the usual Frappe way.

## Workspaces

| Workspace | Roles | Holds |
| --- | --- | --- |
| FoaMES Operator | Operator | Machines running, down and without signal, open stoppages; Floor View, record a stoppage, open suggestions; downtime Pareto and downtime per day |
| FoaMES Supervisor | Supervisor, Engineer | Seven-day OEE, machines running, open stoppages and suggestions; OEE trends by line and machine, Pareto, MTBF and MTTR, suggestion status, process throughput; the Plant dashboard |
| FoaMES Maintenance | Maintenance, Engineer | Plans overdue and due, open work orders, the Maintenance Due List; machines down, stoppages, MTBF and MTTR, availability trend |
| FoaMES Quality | Quality, Engineer | Seven-day quality rate and scrap, open quality suggestions; quality trend, SPC Control Chart, OEE Periods, event logs |
| FoaMES Building | Maintenance, Supervisor, Engineer, Safety | Active building alarms, assets in alarm or stale, facility assets, the zone tree, Utility Consumption, open facility suggestions |
| FoaMES Integration | Integration, Engineer, System Manager | Failed and waiting postings per adapter, failed IDocs, missing External References; outbox health and postings per day |

## Script reports

| Report | Based on | Shows |
| --- | --- | --- |
| OEE Trend | OEE Period | OEE and its factors per machine, line, shift or day, rolled up time-weighted from stored periods |
| Downtime Pareto | Downtime Record | Downtime minutes by reason, category or machine, with cumulative share; no reason shows as Unclassified |
| MTBF and MTTR | Downtime Record | Failures, MTBF (hours), MTTR (minutes), longest stop and inherent availability per machine, over scheduled time only |
| Suggestion Status | Agent Suggestion | Open, accepted, done and dismissed by category, severity or agent, and median hours to resolution |
| Process Throughput | Process Event Log | Cases completed per day or week and cycle-time statistics |
| Andon Response | Andon Call | Median and P90 response and resolution minutes and missed targets by type, machine or line |
| SPC Control Chart | Machine Event | One measurement on an I-MR or X-bar R chart with run-rule signals |
| Maintenance Due List | Maintenance Plan | Enabled plans with live meters, worst first |
| SOP Training Matrix | SOP Acknowledgement | Each person against each Effective SOP they must acknowledge: Current, Outdated, Missing, overdue |
| Utility Consumption | Building Point Reading | Each meter's consumption per day, week or month, charged to the zone it serves, with good units and consumption per good unit where the zone names a line |
| ERP Outbox Health | Outboxes of every adapter | Postings per adapter and status, oldest unposted, most attempts, last error |

A line's OEE is the time-weighted roll-up of its machines' periods (summed ledgers and counts), never an average of percentages. Machines with no **Line** appear under `No Line`.

## Dashboards

**FoaMES Plant**, **FoaMES Maintenance**, **FoaMES Quality** and **FoaMES Integration**, grouping the number cards and charts. Cards labelled "7 Days" cover today and the six days before.

Details: [docs/dashboards.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/dashboards.md).
