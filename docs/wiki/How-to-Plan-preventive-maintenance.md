**Goal:** schedule preventive maintenance on what a machine actually did, and work the due list.

**You need:** FoaMES Maintenance, FoaMES Engineer or System Manager.

## 1. Create a plan per task

Open **Maintenance Plan** (FoaMES Maintenance workspace). One plan is one task on one machine.

| Field | Example |
| --- | --- |
| Title, Machine | Lubricate main bearing, press-1 |
| Trigger | **Calendar** (days), **Run Hours** (real running time from the state ledger) or **Count** (production since last service) |
| Interval | 250 (run hours) |
| Counter | For Count only; leave empty for good plus scrap, or name one such as `strokes` |
| Due Soon At (%), Overdue After (%) | 90 and 10 by default |
| Last Service | The real date of the last service, if you are taking over a schedule |
| Downtime Reason | A planned reason, so the stop leaves the availability base |
| Create Work Order When Due | Tick to have one opened automatically |
| Estimated Minutes, Instructions | Copied onto each work order |

Saving reads the meter at once and shows **Used**, **Remaining**, **Status** and **Due On**.

## 2. Work the work orders

Open a **Maintenance Work Order** from the plan (**Create Work Order**), from the list, or let the hourly check open it.

- **Start** sets it In Progress and, if the plan has a Downtime Reason, opens a Downtime Record for the stop.
- **Complete** closes the stop, restarts the plan's meter and marks its maintenance suggestions Done.

## 3. Watch the due list

Run the **Maintenance Due List** report, worst first. Use **Also Due Within (Days)** to plan the next shutdown. The Maintenance workspace shows plans overdue, due and open work orders.

Every hour FoaMES raises one suggestion per plan per status (Due Soon as Info, Due as Warning, Overdue as Critical). It never stops a machine or writes to a PLC.

With ERPNext on the same site, started work orders can become Asset Repairs; see [Connect ERPNext](How-to-Connect-ERPNext). Details: [docs/maintenance.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/maintenance.md).
