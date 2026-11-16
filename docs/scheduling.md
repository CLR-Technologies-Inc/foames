# Production scheduling

FoaMES plans which machine runs which operation when, against the machines' real working time. A **Production Schedule** holds the operations to plan; **Build** places them on machines with a finite-capacity heuristic; **Publish** makes the result the plan the floor follows. The placed operations are **Scheduled Operations**, which have list, calendar and Gantt views.

The scheduler is not tied to a manufacturing mode. A row is "an operation of a job": the job can be a discrete work order, a batch, a campaign or a lot, and the quantity can be in any unit, as long as the cycle time is per that unit.

Scheduling only plans. It does not start jobs, change machine state or write to an ERP; people publish the plan and follow it, and a rule tells them when a machine falls behind it.

## How a schedule is built

| Input | Where it comes from |
| --- | --- |
| Working time of each machine | Its [Shift Pattern](oee.md#shift-patterns) (shifts and non-working days), else its Shift Start and Scheduled Minutes per Day, else the whole day. Back-to-back shifts form one stretch of working time. |
| Blocked time | Open Maintenance Work Orders (from their start when In Progress, else from their due time, for the plan's Estimated Minutes) and Downtime Records entered ahead with a start and an end. |
| Machines a row may use | The row's Machines list; else every machine of its Machine Type; else every machine in the schedule's scope (its Line, or all enabled machines). |
| Setup and run time | Setup Minutes from the row. Run time is the row's Run Minutes; else Quantity times the row's Cycle Seconds; else the machine-occupied minutes from the machine's default Cycle Time Standard, when cycle time projections are installed; else Quantity times a cycle time from the first `foames_cycle_time_estimators` hook that answers, or the machine's Ideal Cycle Seconds. A machine with no cycle time for a row is left out for that row and listed under Problems. |
| Order inside a job | Operations of one job run in Sequence order, each starting after the previous one ends plus its Transfer Minutes (move, cure or queue time). |

The heuristic is forward list scheduling, as most MES and APS tools do it:

1. Operations whose predecessor in the job is already placed are "ready". An operation that a machine is already working on (the row's Job Reference equals the machine's current job) is pinned to that machine and goes first.
2. The dispatching rule picks the next ready operation:

   | Rule | Picks |
   | --- | --- |
   | EDD | Earliest due date, then highest priority |
   | SPT | Shortest setup plus run time on its fastest machine |
   | FIFO | Row order |
   | Priority | Highest Priority number, then earliest due date |
   | CR | Lowest critical ratio: time to due date divided by the work left in the job |

3. The operation goes on the eligible machine where it finishes earliest, not before its Not Before date. A machine runs one operation at a time.
4. With **Pause Over Breaks** on (the default) work stops at the end of a working window and continues in the next one; the Scheduled Operation is marked as split. With it off, the operation waits for a stretch of working time long enough to hold it.
5. Back-to-back operations on one machine with the same **Setup Group** (for example the same product or colour) share one setup.

An operation that cannot be placed (no eligible machine, or it does not finish inside the horizon) is written as Unscheduled with the reason, and the rest of its job with it.

After a build the schedule shows the counts, the late jobs, the total tardiness in minutes, when the last operation ends and, under Machine Load, each machine's available and busy minutes and utilisation. A Scheduled Operation that ends after its due date has status Late and its Minutes Late.

## Using it

1. Create a Production Schedule: start, horizon in days (up to 90), dispatching rule and optionally a Line.
2. Add the operations by hand, by Data Import, or with **Plan > Get Operations**, which asks every registered demand source (see below). Get Operations replaces the rows that came from a source and keeps the ones typed in by hand.
3. **Plan > Build**, look at the result (**Gantt** opens the Scheduled Operations in Frappe's Gantt view), change rows or the rule and build again as often as needed.
4. **Plan > Publish**. The schedule published before it for the same Line becomes Superseded. A published schedule is not rebuilt; **Copy to New Draft** starts a new one from it.

Engineers and Supervisors create, build and publish schedules; Operators, Maintenance and Quality read them.

## On the floor

The floor snapshot gets `schedule` on each machine: `current` (the operation the published schedule has it on now) and `next` (the next three), so the Floor View, the rules and an external agent see the plan beside the live state.

The **behind schedule** rule raises an Agent Suggestion (category Schedule) when a machine should have been running a scheduled operation for 15 minutes or more but reports Down, Idle, Setup or Unknown. One suggestion per Scheduled Operation.

`GET /api/method/foames.foames_mes.doctype.production_schedule.production_schedule.get_machine_schedule?machine=<name>&days=1` returns the published operations from now on (read on Scheduled Operation).

## Demand from an ERP

`foames_schedule_demand_sources` hooks fill the rows. The ERPNext adapter registers one: it reads the open Job Cards on the Workstations that FoaMES Machines are mapped to (through the Machine's Workstation Reference) and makes one row per card with quantity left:

| Row field | From |
| --- | --- |
| Job | The card's Work Order, so the cards of one order run in their sequence |
| Operation, Sequence | The card's operation and Sequence ID |
| Quantity | For Quantity less Total Completed Qty |
| Run Minutes | The card's Expected Time Required, scaled to the quantity left; empty when ERPNext has none, so the FoaMES cycle times apply |
| Machines | The FoaMES Machines on the card's Workstation |
| Due, Not Before | The Work Order's Expected Delivery Date (else Planned End Date) and Planned Start Date |
| Setup Group | The item made |
| Job Reference | The card's External Reference, so a machine already working on it keeps it |

It only reads ERPNext. Writing the planned times back to ERPNext (Job Card expected start and end) would be a new outbox posting and is not part of this.

Another ERP or a planning tool adds its own source in its app's `hooks.py`:

```python
foames_schedule_demand_sources = ["myapp.planning.open_operations"]

def open_operations(start, end, line):
	return [{"job": "ORDER-1", "operation": "Mix", "sequence": 10, "quantity": 500, "machine_type": "Mixer",
		"due_date": "2026-11-20 17:00:00", "source": "MyERP"}]
```

## Cycle time estimates

When a row has neither Run Minutes nor Cycle Seconds and no Cycle Time Standard answers for the machine, the `foames_cycle_time_estimators` hooks are asked before the machine's Ideal Cycle Seconds. Each is called with the row (as a dict) and the machine row (name, line, machine type, ideal cycle seconds, shift settings) and returns seconds per unit, or None to pass. Use it to feed measured or projected cycle times, for example manual against automatic time per operation, into the plan.

```python
foames_cycle_time_estimators = ["myapp.timing.seconds_per_unit"]
```

## Limits

- One machine runs one operation at a time; there are no secondary resources (tooling, labour) yet.
- Operations of a job run strictly one after another in sequence order; overlapping operations (send-ahead) are not modelled.
- The heuristic is a dispatching rule, not an optimiser: it is fast and explainable, and a different rule can give a better plan for a given mix.
