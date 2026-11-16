**Goal:** use FoaMES with ERPNext installed on the same Frappe site, so machines report against ERPNext Workstations, Job Cards and Assets.

**You need:** ERPNext and FoaMES installed on the same site (in either order), and System Manager.

The ERPNext adapter is built in and switches itself on when the `erpnext` app is present. Reads need no credentials. Writes go through the **ERPNext Outbox** and stay queued until you enable postings, so nothing is lost and nothing is sent by surprise.

## 1. Make ERPNext the default

In **FoaMES Settings**, set **Default ERP System** to `ERPNext`. New External References now point at ERPNext.

## 2. Point machines at their Workstations

On each **Machine**, set **ERP Workstation Reference** to an External Reference of type Workstation whose External ID is the ERPNext Workstation name (for example `Press Line 1`). Save; the reference resolves and shows the Workstation's name. A machine that is a fixed asset can also point at it through **ERP Asset Reference**.

## 3. Choose what FoaMES writes

Open **ERPNext Adapter Settings** and switch on only what you want:

| Setting | What happens |
| --- | --- |
| **Enable Postings to ERPNext** | The scheduler performs queued postings. Off means they wait. |
| **Roll Up Machine Counts to Job Cards** | Every ten minutes, each machine's good and scrap counts and Running stretches become time logs on its current Job Card. |
| **Follow Job Cards Started in ERPNext** | Starting a Job Card in ERPNext sets it as the current job of the machines at that Workstation; completing it ends the job. |
| **Show Machine State on Workstations** | The Workstation status follows the machine: Running as Production, Down as Problem, Unknown as Off. |
| **Post Downtime to ERPNext** | Closed Downtime Records become ERPNext Downtime Entries (set **Downtime Operator**). |
| **Inspect Job Cards from Machine Measurements** | A finished Job Card gets a Quality Inspection from the machine's measurements. |
| **Post Maintenance Work Orders to ERPNext** | A started Maintenance Work Order becomes an Asset Repair on the machine's Asset. |
| **Show Job Cards on the Floor** | The floor snapshot lists open Job Cards per machine. |
| **Pause the Outbox** | Stops performing postings for a while, for example during a stock take. |

## 4. Give a machine a job

Either let ERPNext do it (step 3, **Follow Job Cards**), or set the machine's **Current Job Reference** to a Job Card reference on the Machine form, from a screen through `foames.foames_mes.api.set_current_job`, or from an agent. When the job changes, the old job is rolled up first, so counts never land on the wrong card.

## 5. Check

- The **ERPNext Outbox** list shows postings moving from Queued to Posted.
- The **ERP Outbox Health** report (FoaMES Integration workspace) shows failures and the oldest waiting posting per adapter.
- A Job Card the machine worked on shows new time logs and completed quantity.

A posting that ERPNext rejects goes to **Failed** with ERPNext's message. Fix the cause, then **Requeue** it, or **Cancel** it. Postings for one Job Card are sent strictly in order.

Every setting, payload and rule is in [docs/vendors/erpnext](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/erpnext/README.md).
