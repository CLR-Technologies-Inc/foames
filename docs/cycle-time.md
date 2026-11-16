# Automatic and manual time

A **Cycle Time Standard** splits one operation's time into what the machine does on its own (automatic time) and what an operator does (manual time). From it FoaMES projects how long a quantity takes, how much of that is operator time, what a change such as automating a manual step would save, and how the standard compares with what the machine actually did. The figures are the ones a standard work combination sheet or a time study gives; the arithmetic is in `foames/foames_mes/cycle_time.py`, which has no Frappe dependency.

## The model

An operation is a list of **elements**, each with a standard time in seconds.

| Field | Meaning |
| --- | --- |
| Kind | **Automatic**: the machine works and the operator is free (cutting, moulding, curing, a robot loading). **Manual**: an operator works. |
| While Machine Runs | For manual elements. Off (external): the machine waits for it, such as loading a stopped machine. On (internal): the operator does it while the machine runs, such as deburring the previous part or walking to the next machine. This is the same split SMED makes for setups. |
| Per | **Cycle**: every cycle. **Batch**: once per order, such as setup, first-article inspection or a warm-up. |
| Every N Cycles | For a per-cycle element that happens less often, such as a gauge check every 10 parts (10). |

On the standard: **Parts per Cycle** (a two-cavity mould makes 2), the **Allowance (%)** for personal needs, fatigue and delay, which is added to manual time only, and optional **Labor** and **Machine Rates per Hour** for costs.

One cycle is:

```
cycle = manual external + max(automatic, manual internal)
```

- When internal manual work is shorter than the automatic time, the operator waits for the machine: that is the room to tend more machines. **Machines per Operator** is cycle / operator time, Groover's n'; round it down for a whole number of identical machines.
- When internal manual work is longer, the machine waits for the operator. The standard says so in its notes, because the operator, not the machine, is the bottleneck.
- **Automatic Share (%)** is automatic time over the cycle.

Saving a standard stores these one-cycle figures on it, so they show in the list without recomputing.

### Worked example

A lathe: load 20 s and unload 10 s with the spindle stopped, cut 90 s, deburr the previous part 25 s while the next one cuts, a gauge check of 60 s every 10 parts while it cuts, setup 30 minutes per batch, a 5 minute warm-up per batch, 10 % allowance.

| | Seconds |
| --- | --- |
| Manual external, (20 + 10) x 1.1 | 33.0 |
| Manual internal, (25 + 60 / 10) x 1.1 | 34.1 |
| Automatic | 90.0 |
| Cycle, 33 + max(90, 34.1) | 123.0 |
| Operator per cycle | 67.1 |
| Machines per operator, 123 / 67.1 | 1.83 |

100 parts take 1980 s of manual and 300 s of automatic batch time plus 100 cycles: 243 minutes elapsed, of which 155 minutes automatic and 144.8 minutes operator time.

Automating load and unload with a robot (8 s and 6 s, now Automatic) gives a 104 s cycle with 34.1 s of operator time: 19 s less per cycle and 33 s less operator time per part, or 458 operator hours a year at 50,000 parts.

## Projections

**Project Quantity** on the form, or the API:

`GET or POST /api/method/foames.foames_mes.cycle_time_api.project_time`

| Argument | Meaning |
| --- | --- |
| `standard` or `machine` | The standard by name, or the machine's **Default for Machine** standard |
| `quantity` | Parts to make. Cycles are whole: 7 parts at 2 per cycle are 4 cycles. |
| `changes` | Optional scenario, a JSON list. Each change names an `element` and sets any of `kind`, `seconds`, `internal`, `every`, `per`, or `remove: true`; an element that does not exist is added. A change without `element` may set `parts_per_cycle`, `allowance_percent`, `labor_rate` or `machine_rate`. |
| `annual_quantity` | With `changes`: yearly operator hours, machine hours and cost saved |
| `use_observed`, `days` or `since`/`until`, `min_cycles` | Scale the automatic time to the machine's observed running time over the window first (see below) |

Without `changes` it returns the projection: `cycles`, `setup_minutes`, `run_minutes`, `elapsed_minutes` (machine occupied), `automatic_minutes`, `operator_minutes`, the minutes each side waits, `parts_per_hour`, `labor_cost`, `machine_cost`, `cost_per_part`, the one-cycle `cycle` breakdown and `notes`. With `changes` it returns `baseline`, `scenario` and `delta`, plus `annual` when asked. A scenario never changes the saved standard.

Example scenario body:

```json
{
  "standard": "CTS-00001",
  "quantity": 100,
  "annual_quantity": 50000,
  "changes": [
    {"element": "Load", "kind": "Automatic", "seconds": 8},
    {"element": "Unload", "kind": "Automatic", "seconds": 6}
  ]
}
```

### For a scheduler

`POST /api/method/foames.foames_mes.cycle_time_api.project_operations` takes `operations`, a list of `{"key", "standard" or "machine", "quantity"}`, and returns one projection per row with the `key` echoed back, plus the totals of elapsed, automatic and operator minutes. A row that cannot be projected (no default standard on the machine, no permission) carries an `error` and adds nothing to the totals, so one bad row does not fail a whole schedule. At most 500 rows per call. `elapsed_minutes` is how long the machine is occupied; `operator_minutes` is the labour the job needs, which is what an operator-constrained schedule loads.

## Against the machine

FoaMES already keeps each machine's state ledger and counter deltas (see [oee.md](oee.md)). Over a window:

- **Running** time divided by cycles is the **observed automatic time**. The machine measures this directly.
- **Idle** time divided by cycles is an **upper bound on external manual time**. A machine cannot tell an operator loading it from a machine starved of material or blocked downstream, so this is reported but never used to calibrate.
- **Setup** time is reported apart. Down and Unknown time are not counted at all; unknown time is never production.
- Cycles are good plus scrap counts divided by parts per cycle.

**Compare with Machine** on the form, or `GET foames.foames_mes.cycle_time_api.compare_with_observed` (`standard` or `machine`, and `days` or `since`/`until`), returns the standard's cycle next to the observed figures and the variance in percent (positive is slower than standard). `GET foames.foames_mes.cycle_time_api.get_observed_cycle` (`machine`, window, `parts_per_cycle`) returns the observed figures without a standard.

`use_observed` on a projection scales the standard's automatic per-cycle elements so they add up to the observed automatic time, and leaves manual time and batch elements at standard. Below `min_cycles` observed cycles (default 20) the standard is used unchanged, and the projection's notes say which happened.

## Permissions

Engineers and System Managers create and edit standards; Supervisors, Operators and Maintenance read them. Projections need read on Cycle Time Standard; anything that reads the machine's history also needs read on Machine Event. Nothing in this feature writes to a machine or an ERP.

## ERP links

A standard may point at an **ERP Operation** and an **ERP Item** through External References (types Operation and Item), so a scheduler or an adapter can match it to a routing operation without FoaMES linking to an ERP DocType. The projections are returned with those references.

## MCP

`foames_project_time` and `foames_compare_cycle_with_machine` expose the projection and the comparison to agents. Both read only.
