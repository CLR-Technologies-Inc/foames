# Statistical process control on machine measurements

FoaMES charts every Measurement-type Machine Event (a temperature, a pressure, a diameter from an
inline gauge) with Shewhart control charts and raises an Agent Suggestion when a run rule signals.
It needs no setup beyond sending Measurement events with a stable `name`; see
[machine-data.md](machine-data.md) for the event shape.

## Charts

| Chart | When | Limits |
| --- | --- | --- |
| I-MR (individuals and moving range) | One reading at a time, the default | CL = mean, UCL/LCL = mean ± 3 · MR̄ / d2; MR chart UCL = D4 · MR̄ |
| X-bar R | Readings grouped into consecutive subgroups of 2 to 25 | CL = grand mean, UCL/LCL = X̿ ± A2 · R̄; R chart UCL = D4 · R̄, LCL = D3 · R̄ |

The factors (d2, d3, A2, D3, D4) match the AIAG SPC manual tables; d2 is computed exactly, d3 is
tabulated. The arithmetic follows CLR Technologies' ops-library (`02-quality-and-statistics/tools/python`),
and the tests check FoaMES against that library's reference limits.

## Run rules

Choose the set in **Machine Data Settings → Statistical Process Control → Run Rules**.

| Rule | Signal |
| --- | --- |
| N1 / WE1 | One point beyond the 3-sigma limits (raised as Critical) |
| N2 | Nine points in a row on one side of the centre line |
| WE4 | Eight points in a row on one side of the centre line |
| N3 | Six points in a row steadily increasing or decreasing |
| N4 | Fourteen points in a row alternating up and down |
| N5 / WE2 | Two of three points in a row beyond 2 sigma on the same side |
| N6 / WE3 | Four of five points in a row beyond 1 sigma on the same side |
| N7 | Fifteen points in a row within 1 sigma (stratification) |
| N8 | Eight points in a row beyond 1 sigma on either side (mixture) |

Moving ranges and subgroup ranges overlap or are skewed, so only the beyond-the-limit rule is applied
to the MR and R charts. A point exactly on a limit or on the centre line counts as inside.

## Suggestions

The hourly suggestion run (`foames.foames_mes.tasks.run_suggestion_rules`, also
`foames.foames_mes.api.run_suggestion_rules`) does this for every machine measurement with a reading
in the recent window:

1. Readings from the **Baseline Window (days)** before the recent window set the limits (Phase II:
   new readings are judged against past behaviour, not their own). With fewer than **Minimum
   Baseline Readings** nothing is raised.
2. Readings from the **last N hours** are checked against the run rules.
3. One Agent Suggestion (category Quality) is raised per machine, measurement, chart and rule, with
   `rule_key` `spc:<machine>:<measurement>:<chart>:<rule>`. The evidence carries the latest signalled
   reading, up to ten recent signals, the centre line, the limits, sigma and the baseline size.
4. While a suggestion is open, further signals do not add another. A suggestion that was accepted,
   dismissed or done stays closed until the rule signals again on a reading after it was resolved.

Set **X-bar R Subgroup Size** to 2..25 to also run an X-bar R chart over consecutive readings, and
clear **SPC Suggestions Enabled** to turn the rule off.

## Report and API

The **SPC Control Chart** script report (FoaMES Quality workspace) draws one measurement of one
machine as an I-MR or X-bar R chart, with the signalled rules per point, the MR or R column, and a
summary of sigma and signals. **Baseline Readings** takes the limits from the first N readings; 0 uses
every reading in the window (Phase I trial limits).

`foames.foames_mes.spc_monitor.get_control_chart(machine, measurement, from_date, to_date, chart,
subgroup_size, baseline_points, rules)` returns the same chart as JSON for agents and dashboards.

## Code

| Module | Contents |
| --- | --- |
| `foames/foames_mes/spc.py` | Chart factors, I-MR and X-bar R charts, the run rules and `findings`. No Frappe dependency. |
| `foames/foames_mes/spc_monitor.py` | Reads Measurement events, applies the settings, filters resolved findings, and the JSON endpoint. |
| `foames/foames_mes/report/spc_control_chart/` | The script report. |
