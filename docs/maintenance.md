# Preventive maintenance

FoaMES keeps preventive maintenance plans per machine and reads their meters from the data it already collects, so a plan falls due on what the machine actually did, not on a guess. A plan is due by one of three triggers:

| Trigger | The meter | Where it comes from |
| --- | --- | --- |
| Calendar | Days since the last service | The clock |
| Run Hours | Running hours since the last service | The OEE state ledger: State and Alarm events with Downtime Records overlaid. Idle, Setup, Down and Unknown time never count, so a machine that stops reporting stops wearing on paper too. |
| Count | Production since the last service | The stored counter deltas on Count events. Good plus scrap by default (all output wears the machine), or one named counter such as `strokes` or `cycles`. A reset or an out-of-order reading adds nothing, as everywhere in FoaMES. |

Shift calendars are not used yet: a Calendar plan counts calendar days, and Run Hours count real running time whatever the shift.

## Setting up a plan

Open **Maintenance Plan** (FoaMES Maintenance workspace, Preventive Maintenance card) and fill in:

- **Title** and **Machine**. One plan is one task on one machine; a machine has as many plans as it has tasks (lubrication every 250 run hours, a filter every 30 days, a die inspection every 100,000 strokes).
- **Trigger** and **Interval**: days, run hours or counts between services. For Count, optionally a **Counter**; leave it empty to count good plus scrap.
- **Due Soon At (%)** (default 90) and **Overdue After (%)** (default 10). With the defaults a plan is OK below 90 percent of its interval, Due Soon from 90 percent, Due from 100 percent and Overdue from 110 percent.
- **Last Service**: where the meter starts. A new plan starts counting when it is saved; set it to the real date of the last service when you take over an existing schedule.
- **Downtime Reason**: optional. While a work order for the plan is In Progress, FoaMES records the stop as a Downtime Record with this reason. Use a reason that counts as planned, so OEE takes the stop out of availability instead of charging it as a breakdown.
- **Create Work Order When Due**: optional. The hourly check opens a work order by itself when the plan reaches Due and none is open.
- **Estimated Minutes** and **Instructions**: copied onto each work order.

Saving the plan reads its meter at once: **Used**, **Used (%)**, **Remaining**, **Status** and **Due On**. For a Calendar plan Due On is exact. For a usage plan it is projected at the average rate since the last service, and is empty until the machine has run.

## The hourly check

`foames.foames_mes.tasks.check_maintenance_plans` runs hourly. For every enabled plan it reads the meter, stores it on the plan, opens a work order where the plan asks for one, and raises an **Agent Suggestion** (category Maintenance) for each plan that is Due Soon (severity Info), Due (Warning) or Overdue (Critical). Each status raises once per service cycle, so a plan that goes from Due Soon to Overdue produces three suggestions over its life, never one per hour. The suggestion names the meter, the interval, the projected date and the open work order if there is one.

In line with the rule that agents suggest and people act, nothing else happens on its own: FoaMES does not stop the machine or write to the PLC.

## Work orders

A **Maintenance Work Order** is one service of a plan. Create one from the plan (**Create Work Order**), from the list, or let the hourly check open it. It moves through Open, In Progress, Completed and Cancelled; the form has **Start** and **Complete** buttons.

- **Start** (In Progress) stamps Started On and, when the plan has a Downtime Reason, opens a Downtime Record for the stop. If the machine already has an open stop, that record is used and given the reason if it had none.
- **Complete** stamps Completed On and Completed By, works out Actual Minutes, closes the Downtime Record, restarts the plan's meter from Completed On and marks the plan's open maintenance suggestions Done. A work order completed without being started first still gets a closed Downtime Record from Started On to Completed On when those are filled in.
- A completion entered late, older than the plan's Last Service, is kept as history but does not move the meter back.
- A completed work order cannot be reopened; raise a new one. Cancelling closes the stop.

## The Maintenance Due List

The **Maintenance Due List** report lists the enabled plans with their meters read at the moment the report runs, worst first: Overdue, Due, Due Soon, then by how far through the interval they are. Filter by machine, line or trigger. **Show** chooses Due Soon or later (the default), Due or Overdue, or all plans; **Also Due Within (Days)** adds OK plans whose due date falls within that many days, for planning the next shutdown. Each row links the plan and its open work order.

The FoaMES Maintenance workspace shows three number cards (plans overdue, plans due or due soon, open work orders) and shortcuts to the due list, the open work orders and the plans.

## Who can do what

| Role | Maintenance Plan | Maintenance Work Order | Due List |
| --- | --- | --- | --- |
| FoaMES Maintenance, FoaMES Engineer, System Manager | Create, edit, delete | Create, edit, delete | Run |
| FoaMES Supervisor | Read | Create, edit | Run |
| FoaMES Operator | Read | Read | Run |

## For integrators

- `foames.foames_mes.maintenance` holds the arithmetic (`assess`, `projected_due`, `findings`) with no Frappe dependency.
- `foames.foames_mes.doctype.maintenance_plan.maintenance_plan.make_work_order(plan)` is whitelisted: it opens a work order for the plan, or returns the one already open.
- An external agent can read plans and work orders through the standard REST API (`/api/resource/Maintenance Plan`) and the due list through `frappe.desk.query_report.run` with `report_name="Maintenance Due List"`.
