# Where does the welding cell lose time?

`data/weld_cell_events.csv` is an export of a welding cell's work orders: one row per event with `case_id` (the work order), `activity`, `lifecycle` (`start` or `complete`), `timestamp` (UTC) and `resource`. The rows are not sorted.

The production engineer wants numbers, not a slide. Write `analysis/analyze.py` so that running `python analysis/analyze.py` from the repository root (with `PYTHONPATH=.foames-bench/stubs:.`) reads the CSV and writes `answers.json` in the repository root, then run it and commit both. `answers.json` must hold:

- `cases`: the number of work orders.
- `variants`: the number of distinct activity sequences, counting each activity once per `complete` event.
- `top_variant`: `{"activities": [...], "cases": n}` for the most frequent sequence.
- `median_cycle_time_minutes`: the median, over work orders, of the time from a work order's first event to its last, in minutes.
- `rework_cases`: for each activity completed more than once within a work order, the number of work orders where that happens.
- `bottleneck`: the activity with the most total waiting time in front of it, waiting being the time from the previous step's completion to this activity's start.
- `incomplete_cases`: the work orders that never reached Pack, sorted.

FoaMES has a process-mining module; use it if it helps. Do not change code under `foames/`.
