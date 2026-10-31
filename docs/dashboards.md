# Dashboards, reports and role workspaces

FoaMES ships standard Frappe workspaces, number cards, dashboard charts, dashboards and script reports for the public features: OEE by machine and line, the downtime Pareto, MTBF and MTTR, Agent Suggestion status, the ERP outbox health and process-mining throughput. Everything here is a standard Frappe record that `bench migrate` installs and keeps in sync, so nothing has to be built by hand on a site, and all of it can be copied and changed in the usual Frappe way (duplicate a workspace, add a chart, change a filter).

## Workspaces by role

Each workspace is public and limited to its roles, so a user sees only the pages for the jobs they do. FoaMES Engineers see the Supervisor, Maintenance, Quality and Integration pages; System Managers see everything.

| Workspace | Roles | What is on it |
| --- | --- | --- |
| FoaMES Operator | FoaMES Operator | Machines running, down and without signal, open stoppages; shortcuts to the Floor View, recording a stoppage, the open and unclassified stoppages and open suggestions; the downtime Pareto and the downtime per day |
| FoaMES Supervisor | FoaMES Supervisor, FoaMES Engineer | Average OEE over the last seven days, machines running, open stoppages and open suggestions; OEE trends by line and by machine, the downtime Pareto, MTBF and MTTR, suggestion status and process throughput; shortcuts to every report and the Plant dashboard |
| FoaMES Maintenance | FoaMES Maintenance, FoaMES Engineer | Machines down, open and unclassified stoppages, downtime minutes this week; MTBF and MTTR, the Pareto by reason and by machine, downtime per day, stoppages by machine, availability trend |
| FoaMES Quality | FoaMES Quality, FoaMES Engineer | Quality rate and scrap over the last seven days, open quality suggestions; the quality rate trend, suggestions by category and status, process throughput; links to OEE Periods, Process Event Logs and Event Log Sources |
| FoaMES Integration | FoaMES Integration, FoaMES Engineer, System Manager | Failed and waiting postings per adapter, failed IDocs, missing External References; outbox health, postings per day, inbound IDocs per day; the settings of both adapters |

Two roles are new with these pages. **FoaMES Supervisor** reads everything in the MES module and may edit Downtime Records, Downtime Reasons, Agent Suggestions and Process Event Logs. **FoaMES Maintenance** reads machines, events and OEE Periods, and may create and edit Downtime Records and Downtime Reasons and work on Agent Suggestions. Sites installed before this release get both roles from the `create_supervisor_and_maintenance_roles` patch on `bench migrate`. The role table in [installation.md](installation.md) has the full list.

## Lines

The Machine has a `Line` field, a free text such as `Line 2` or `Cell B`. The OEE Trend, Downtime Pareto and MTBF and MTTR reports filter by it and the OEE Trend rolls machines up by it. A line's OEE is the time-weighted roll-up of its machines' OEE Periods (summed ledgers and counts), never an average of percentages, so a short trial run on one machine cannot move the line as much as a full shift on another. Leave the field empty and the line reports show the machines under `No Line`.

## Reports

All six are script reports with a chart and a summary row, so each one can be placed on a workspace or dashboard as a Report chart. Dates default to the last 30 days (90 for suggestions, 7 for the outbox) when a chart calls them without dates.

| Report | Based on | Filters | Rows |
| --- | --- | --- | --- |
| OEE Trend | OEE Period | date range, machine, line, group by Machine / Line / Day, chart metric OEE / Availability / Performance / Quality | one row per group and day, rolled up from the stored periods: OEE, availability, performance, quality, the time ledger and counts. The chart draws one line per group (the eight busiest when there are more) |
| Downtime Pareto | Downtime Record | date range, machine, line, group by Reason / Category / Machine, include planned, include open | downtime minutes per group largest first, with the share and cumulative share. Records are clipped to the window; records without a reason appear as `Unclassified` |
| MTBF and MTTR | Downtime Record | date range, machine, line, breakdown reasons only | per machine: failures (closed, unplanned stoppages), MTBF in hours, MTTR in minutes, downtime, longest stop, inherent availability `MTBF / (MTBF + MTTR)`. Operating time is the window at the machine's Scheduled Minutes Per Day (the whole day without one) less the downtime |
| Suggestion Status | Agent Suggestion | raised date range, group by Category / Severity / Agent, category, severity, agent | per group: open, accepted, done and dismissed counts, the share accepted or done, the median hours from raising to resolution |
| Process Throughput | Process Event Log | event log (the latest extracted one by default), daily or weekly, only cases with an activity | cases completed per period (a case completes at its last event), events, median, mean, P90 and longest cycle time in hours; the summary carries the log's cases per day |
| ERP Outbox Health | S4HANA Outbox (reads the ERPNext Outbox too) | created date range, adapter, operation | per adapter and status: postings, age of the oldest unposted one, the most attempts, the next attempt and the last error. Unposted work outside the date range is always included |

The OEE Trend does not recompute anything: it reads the OEE Periods the daily task created, so the report and the OEE Period list always agree. To see a day that has no period yet, run `compute_daily_oee` for it or use OEE on demand ([oee.md](oee.md)).

Report permissions follow Frappe's rules: a user needs the report's role and *report* permission on its base DocType. Operators and Quality staff can run the OEE Trend and the Pareto; MTBF and MTTR is for Supervisors, Maintenance and Engineers; the outbox report is for Integration users, Engineers and System Managers.

## Number cards and charts

The cards are plain `Document Type` cards (counts, sums and averages over a DocType with a filter), so the Dashboard Manager can open any of them and change the filter or the colour. Cards that say "7 Days" use a dynamic date filter evaluated in the browser.

| Module | Cards | Charts |
| --- | --- | --- |
| FoaMES MES | Machines Running, Machines Down, Machines Without Signal, Open Stoppages, Unclassified Downtime Last 7 Days, Downtime Minutes Last 7 Days, OEE Last 7 Days, Quality Rate Last 7 Days, Scrap Last 7 Days, Open Suggestions, Critical Open Suggestions, Open Quality Suggestions | Report charts: OEE Trend by Machine, OEE Trend by Line, Availability Trend by Machine, Quality Rate Trend by Machine, Downtime Pareto by Reason / Machine / Category, MTBF and MTTR by Machine, Suggestion Status by Category / Agent, Process Throughput per Day. DocType charts: Downtime Minutes per Day, Machine Events per Day, Suggestions Raised per Week, Open Suggestions by Category, Stoppages by Machine |
| FoaMES Adapters | ERPNext Postings Failed / Waiting, S4HANA Postings Failed / Waiting, S4HANA IDocs Failed, Missing External References | ERP Outbox Health by Adapter, ERPNext Postings per Day, S4HANA Postings per Day, Inbound IDocs per Day |

Four dashboards (Dashboard list, or the shortcut on each workspace) group them: **FoaMES Plant**, **FoaMES Maintenance**, **FoaMES Quality** and **FoaMES Integration**.

## Making your own

- To add a chart for one line only, duplicate one of the Report charts and put `{"group_by": "Machine", "line": "Line 2"}` in its filters; any report filter works there.
- A new script report under `foames/foames_mes/report/` can reuse `foames/foames_mes/report/utils.py` (the date window, the machine and line scope, the chart shape) and the arithmetic in `foames/foames_mes/kpi.py`, which has no Frappe dependency and its own unit tests.
- Workspaces are edited on the site with Workspace Manager rights. With `developer_mode` on, saving a standard record writes it back to the app folder, which is how these files are maintained.
