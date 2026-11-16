## What you are given

`data/case/case.json` describes the case: the cited source and the figure it claims, the baseline and after windows (`[start, end)`, UTC), the plant's planned hours (`planned_hours`, hours of the day in UTC, on the weekdays in `planned_weekdays`, Monday = 0), `mark_unknown_after_minutes`, the units, the energy price, and two machines: the `line` (state events, and running-total counters `good` and `scrap`) and the `meter` (a running-total energy counter, with the machine's `counter_rollover`).

`data/case/events.csv` is the plant's FoaMES Machine Event export: `seq` (arrival order), `source_id`, `timestamp`, `event_type` (`State` or `Count`), `state` and `planned` (for State events; `planned` is 1 for a planned Down), `counter_name` and `counter_value` (for Count events). The data is illustrative: invented events, grounded in the figures of the cited source. Do not change anything under `data/`.

## What to deliver

1. `analysis/case_study.py`. Running `python analysis/case_study.py` from the repository root (with `PYTHONPATH=.foames-bench/stubs:.`) reads `data/case/` and writes `case_study.json` in the repository root. It must also accept `--data DIR` and `--out FILE`, because it will be run on other exports of the same shape. Commit the script and the JSON it wrote.
2. `CASE_STUDY.md`, a write-up that follows `docs/case-studies/_template.md`, labelled Illustrative, with the source cited by its URL and its figure presented as a claim next to what you measured.

`case_study.json` holds `case_id`, `windows.baseline` and `windows.after`, `annual_energy_saving`, `annual_cost_saving` and `claim_check`. Each window holds:

- `planned_minutes`: the window's minutes inside planned hours.
- `run_minutes`, `idle_minutes`, `setup_minutes`, `planned_downtime_minutes`, `unplanned_downtime_minutes`, `unknown_minutes`: the line's planned minutes by state. A state holds from its event until the line's next State event, but it is trusted for at most `mark_unknown_after_minutes` after the line's latest event of any type; time beyond that, until the next event, has no signal.
- `good`, `scrap`, `energy`: counter deltas whose reading's timestamp falls in the window, computed the way FoaMES's Machine Event computes them (see `foames/foames_mes/counters.py` and the Machine Event DocType), processing readings in arrival order. `energy` is the meter's counter.
- `availability`, `performance`, `quality`, `oee`: as `foames.foames_mes.oee.compute_oee` computes them, with the line's `ideal_cycle_seconds` per unit.
- `specific_energy`: energy per good unit. `good_per_planned_hour`: good output per planned hour.
- `changeovers`: the line's State events that enter Setup from another state, timestamped in the window and in planned time. `mean_setup_minutes`: `setup_minutes / changeovers`.

Use `null` where a value cannot be computed (a division by zero).

- `annual_energy_saving` = (baseline `specific_energy` - after `specific_energy`) x after `good` x (525,600 / the after window's length in minutes). `annual_cost_saving` = that x `energy_price`.
- `claim_check` = `{"kind", "claimed", "measured", "ratio", "verdict"}`. `kind` and `claimed` are the claim's `kind` and `value`. `measured` is, for `annual_energy_saving`: `annual_energy_saving`; for `oee_after`: the after window's `oee`; for `setup_reduction`: 1 - after `mean_setup_minutes` / baseline `mean_setup_minutes`; for `throughput_ratio`: after `good_per_planned_hour` / baseline `good_per_planned_hour`; for any other kind, `null`. `ratio` = `measured / claimed`. `verdict` is `"supported"` when 0.8 <= ratio <= 1.25, `"not supported"` otherwise, and `"not measurable"` when `measured` is `null`.

You may use FoaMES's modules. Do not change code under `foames/`. Put any tests you write under `analysis/`.
