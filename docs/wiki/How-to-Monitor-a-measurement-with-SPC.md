**Goal:** chart a machine measurement (a temperature, a pressure, a diameter from an inline gauge) on a control chart and get a Quality suggestion when a run rule signals.

**You need:** a machine that sends **Measurement** events with a stable `name`, for example `{"machine": "press-1", "type": "Measurement", "name": "temperature", "value": 72.5}`, and FoaMES Engineer or System Manager for the settings.

## 1. Choose the rules

Open **Machine Data Settings**, section **Statistical Process Control**:

| Setting | Default | Meaning |
| --- | --- | --- |
| SPC Suggestions Enabled | on | Turn the hourly check on or off |
| Run Rules | Nelson | Nelson (N1 to N8) or Western Electric (WE1 to WE4) |
| X-bar R Subgroup Size | 0 | 2 to 25 to also run an X-bar R chart over consecutive readings |
| Baseline Window (days) | 7 | Readings before the recent window that set the limits |
| Judge Readings From the Last (hours) | 2 | Readings checked against the rules |
| Minimum Baseline Readings | 20 | Below this, nothing is raised |

## 2. Look at the chart

Open the **SPC Control Chart** report (FoaMES Quality workspace). Pick the machine and the measurement, the dates and I-MR or X-bar R. Set **Baseline Readings** to the number of readings that should set the limits, or 0 to use every reading in the window as trial limits. Signalled rules are shown per point.

## 3. Act on signals

Every hour, FoaMES judges the recent readings against limits set by the baseline and raises one Agent Suggestion (category Quality) per machine, measurement, chart and rule. A point beyond 3 sigma is raised as Critical. The evidence carries the signalled readings, the centre line, the limits and sigma. Work it like any suggestion: Accepted, Done or Dismissed, with a resolution.

## For agents and dashboards

`foames.foames_mes.spc_monitor.get_control_chart(machine, measurement, from_date, to_date, chart, subgroup_size, baseline_points, rules)` returns the same chart as JSON.

The formulas and rule definitions are in [docs/spc.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/spc.md).
