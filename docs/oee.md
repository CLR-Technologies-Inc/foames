# OEE in FoaMES

Overall Equipment Effectiveness (OEE) in FoaMES is computed from the machine's own events: its state history, the downtime records opened around it, and the counter deltas it reported. Nothing is typed in by hand, and no minute is assumed. This page explains what goes into the number, how to set a machine up so the number means something, and how to read a period.

## The arithmetic

| Factor | Formula |
| --- | --- |
| Availability | run minutes / (planned minutes − planned downtime minutes) |
| Performance | (ideal cycle seconds × total count / 60) / run minutes, capped at 100 % |
| Quality | good count / (good count + scrap count) |
| OEE | availability × performance × quality |

All four are stored as percentages on the OEE Period. The arithmetic lives in `foames/foames_mes/oee.py`, which has no Frappe dependency, so it can be read and tested on its own.

### The time ledger

Every minute of the planned period is assigned to exactly one bucket from the machine's state history:

| Machine state during the minute | Bucket | Effect on availability |
| --- | --- | --- |
| Running | Run | Counts as run time |
| Down, inside a Downtime Record whose reason **Counts As Planned Downtime** | Planned downtime | Removed from the base, so it does not reduce availability |
| Down, otherwise | Unplanned downtime | Loss |
| Idle | Idle | Loss (not stored as downtime, but not run time either) |
| Setup | Setup | Loss, same as Idle |
| Unknown, or no event at all | Unknown | Loss. Time without a machine signal is never counted as run time |

The state in force at the start of the period is the last state event before it, so a machine that was Running since the previous shift is Running from minute one. An Alarm event counts as Down.

**Signal Coverage** on the period is the share of planned minutes with a known state. A low coverage means the OEE is low because the machine was silent, not necessarily because it was stopped. Fix the data path before acting on the number.

### Counts

Counts are the sum of the counter deltas inside the period, not the difference between the first and last raw reading, so a counter reset or a first reading contributes zero rather than a jump. Counter names are grouped as follows:

| Counter names | Counted as |
| --- | --- |
| `good`, `count`, `total`, `parts` | Good |
| `scrap`, `reject`, `bad`, `ng` | Scrap |
| anything else | Not in OEE (still stored and available for your own reports) |

If a machine reports only a total and a scrap counter, send the total as `count` and the scrap as `scrap`: good is then total minus scrap in effect, because quality divides good by good plus scrap. If it reports good and total, send good as `good` and derive scrap on the gateway; FoaMES does not subtract counters for you.

### Notes the computation adds

A period may carry notes, returned by `get_oee` and kept on the document's flags during save:

- *performance above 100 percent: check the ideal cycle time or the counters*. The machine produced more than its ideal cycle time allows. Performance is capped at 100 %, and either the ideal cycle time is too long or a counter is double-counting.
- *no ideal cycle time on the machine: performance assumed 100 percent*. Set **Ideal Cycle Time** on the Machine; until then performance is not measured.
- *N minutes without a machine signal counted as loss*. The unknown bucket is not empty.

## Setting a machine up for OEE

On the **Machine** record:

| Field | Why it matters |
| --- | --- |
| **Ideal Cycle Time (s)** | Seconds per unit at rated speed. Without it, performance is reported as 100 % and flagged in the notes. |
| **Shift Start** and **Scheduled Minutes Per Day** | Define the daily OEE window. With a shift start of 06:00 and 480 minutes, the daily period runs 06:00 to 14:00 and nothing outside it is counted. Leave Shift Start empty to measure the whole day against 1440 planned minutes. |
| **Counter Rollover** | The value at which the machine's counter wraps to zero, so a wrap is counted as production rather than as a reset. Leave 0 for a counter that never wraps. |
| **Source ID** | Must match what the gateway sends; otherwise the events are rejected and the machine has no history. |

On **Downtime Reasons**, tick **Counts As Planned Downtime** for the reasons that should not count against availability. Only downtime with such a reason assigned is excluded; an open Downtime Record with no reason yet is unplanned loss until an operator assigns one. The Category field (Planned, Unplanned, Changeover, Breakdown, No Material, No Operator, Quality, Other) is for reporting and does not affect OEE by itself.

In **Machine Data Settings**, **Mark Machine Unknown After** decides how quickly a silent machine stops being counted as whatever it last reported. The default is 15 minutes, checked every 5 minutes by the scheduler.

## The daily OEE Period

Once a day the scheduler creates one **OEE Period** per enabled machine for the previous day, over the machine's scheduled window. Its name is `OEE-<machine>-<from time>`. A period is not created twice for the same machine and window, so re-running the job is harmless.

Each period shows the time ledger (run, planned downtime, unplanned downtime, unknown minutes, coverage), the good and scrap counts, and the four factors. The ideal cycle time is copied from the machine when the period is computed, so a later change to the machine does not silently change old periods.

A period is computed when it is saved. If events arrive late (a replay through the webhook, a gateway that was down), open the period and save it again to recompute, or create a period by hand for any window: pick the machine, the from and to times and the planned minutes, and the rest is filled in on save.

To create the periods for a particular day from the bench:

```bash
bench --site $SITE execute foames.foames_mes.doctype.oee_period.oee_period.compute_daily_oee --kwargs "{'for_date': '2026-10-30'}"
```

## OEE on demand

`foames.foames_mes.doctype.oee_period.oee_period.get_oee` computes OEE for any window without saving a period. It needs read permission on OEE Period.

```
GET /api/method/foames.foames_mes.doctype.oee_period.oee_period.get_oee
    ?machine=press-1
    &from_time=2026-10-30 06:00:00
    &to_time=2026-10-30 14:00:00
    &planned_minutes=480
```

`planned_minutes` defaults to the length of the window. The response holds `availability`, `performance`, `quality`, `oee`, `run_minutes`, `unknown_minutes`, `coverage`, `good_count`, `scrap_count` and `notes`.

The Floor View shows each machine's most recent period as "OEE n %" on its tile, and the floor snapshot returns it as `oee_today` with all four factors (see [floor-view.md](floor-view.md)).

## A worked example

A press with an ideal cycle time of 2 seconds, shift 06:00 to 14:00 (480 planned minutes):

| Interval | State | Minutes | Bucket |
| --- | --- | --- | --- |
| 06:00–06:30 | Setup | 30 | Setup (loss) |
| 06:30–10:00 | Running | 210 | Run |
| 10:00–10:45 | Down, reason "Planned maintenance" (planned) | 45 | Planned downtime |
| 10:45–13:00 | Running | 135 | Run |
| 13:00–13:20 | Down, reason "Jam" | 20 | Unplanned downtime |
| 13:20–14:00 | no events, machine marked Unknown | 40 | Unknown (loss) |

Counters over the shift: good deltas sum to 9,000, scrap deltas to 300.

- Availability = 345 / (480 − 45) = 79.3 %
- Performance = (2 × 9,300 / 60) / 345 = 310 / 345 = 89.9 %
- Quality = 9,000 / 9,300 = 96.8 %
- OEE = 0.793 × 0.899 × 0.968 = 69.0 %
- Coverage = 440 / 480 = 91.7 %, with the note *40 minutes without a machine signal counted as loss*

The 40 silent minutes at the end cost about 7 points of OEE. If the press was in fact running and the gateway had dropped, the fix is the gateway, and the period can be recomputed once the events are replayed with their original timestamps.

## What OEE in FoaMES does not do

- It does not count the silent time as run time, ever, and it does not let an operator type a run time in.
- It does not infer scrap from a mismatch between counters.
- It does not aggregate across machines or lines. Sum what you need from the OEE Period list or from your own report; a line OEE is a design decision about bottlenecks that FoaMES leaves to the plant.
