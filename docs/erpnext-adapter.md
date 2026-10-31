# ERP adapters and the ERPNext adapter

FoaMES keeps no Link fields to ERP DocTypes. When a FoaMES record needs to point at something in an ERP, it points at an **External Reference**, and the ERP's adapter turns that reference into a real record. This page explains External References, how the built-in ERPNext adapter works, how to run with no ERP, and how to write an adapter for another ERP. The SAP S/4HANA adapter has its own page: [s4hana-adapter.md](s4hana-adapter.md).

## External Reference

An External Reference is a triple:

| Field | Meaning |
| --- | --- |
| **ERP System** | The key of a registered adapter: `ERPNext`, `S4HANA`, or the key of an adapter another app registers. Defaults to **Default ERP System** in FoaMES Settings. |
| **Reference Type** | One of the kernel's reference types (below). |
| **External ID** | The record's identifier in that ERP. For ERPNext this is the document name, for example the Item code or the Work Order name. |

The kernel reference types are Item, Unit of Measure, Batch, Serial Number, Work Order, Operation, Location, Stock Movement, Job Card, Bill of Materials, Routing and Workstation. An adapter declares which of them it supports; saving a reference of an unsupported type for that ERP is refused.

Each reference also carries:

- **Status**: `Unverified` until it has been looked up, then `Resolved` when the record exists in the ERP or `Missing` when it does not.
- **Label**: the human-readable name the adapter returned (the Item name, the warehouse name, and so on).
- **Last Resolved On**: when the lookup last ran.
- **Reference Key**: a hash of the triple that makes the reference unique. The same ERP record is referenced exactly once per site, and a second attempt to create it is rejected as a duplicate.

### When references are resolved

By default a reference is looked up in its ERP every time it is saved, as long as the adapter reports that its ERP is available. If the ERP is reachable but the record is not there, the status becomes `Missing`. If a remote ERP is down, saving still succeeds and the reference stays `Unverified` to be resolved later.

Two controls change this:

- **Skip Resolving References on Save** in FoaMES Settings turns the automatic lookup off. References are then resolved only through the **Resolve** button on the form, or by code calling the document's `resolve` method.
- Changing the ERP System, Reference Type or External ID of an existing reference clears its resolution, so a corrected reference is never shown as Resolved on the strength of its old value.

References that resolve as `Missing` show up in the floor snapshot and trigger the built-in ERP rule, which raises one Agent Suggestion listing them (see [floor-view.md](floor-view.md)).

### Where references are used

- A **Machine** can carry an **ERP Workstation Reference** and an **ERP Location Reference**. The first must be a Workstation reference and the second a Location reference; the form refuses anything else.
- The S/4HANA adapter records a reference for every order, material or batch IDoc it receives, and for every material document its outbox creates.
- Other apps built on FoaMES link to External Reference in the same way instead of linking to ERP DocTypes directly.

### Creating references from code

```python
from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

# Name of the External Reference for Item "FG-100" in the default ERP, created if it does not exist.
name = get_reference("Item", "FG-100")

# The same for an explicit ERP.
name = get_reference("Work Order", "MFG-WO-2026-00012", erp_system="ERPNext")
```

`get_reference` is safe under concurrency: if two workers create the same reference at once, both get the same record. Only System Managers may create External References through the desk; code that has done its own permission check can pass `ignore_permissions=True`.

For pickers in a UI, `foames.foames_adapters.get_available_erp_systems` returns every registered adapter with its key, label and whether its ERP is reachable from the site.

## The ERPNext adapter

The ERPNext adapter is built in and needs no configuration. It is registered under the key `ERPNext` and reports itself available when the `erpnext` app is installed on the same site. Set **Default ERP System** in FoaMES Settings to `ERPNext` so new references use it without being told.

Resolution is a direct read of ERPNext's tables, so it is fast and needs no credentials. The adapter maps each kernel reference type to an ERPNext DocType and takes the label from one of its fields:

| Reference type | ERPNext DocType | Label |
| --- | --- | --- |
| Item | Item | Item Name |
| Unit of Measure | UOM | UOM Name |
| Batch | Batch | Batch ID |
| Serial Number | Serial No | Serial No |
| Work Order | Work Order | Production Item |
| Operation | Operation | Description |
| Location | Warehouse | Warehouse Name |
| Stock Movement | Stock Entry | Stock Entry Type |
| Job Card | Job Card | Operation |
| Bill of Materials | BOM | Item |
| Routing | Routing | Routing Name |
| Workstation | Workstation | Workstation Name |

The External ID is the ERPNext document name in every case (`FG-100`, `MFG-WO-2026-00012`, `Stores - ACME`, `BOM-FG-100-001`).

The adapter is built in and switches on by itself when the `erpnext` app is installed on the same site. Nothing is imported from ERPNext at module load and no FoaMES DocType links to an ERPNext DocType, so FoaMES still installs and passes its tests on a plain Frappe site; CI runs the suite with and without ERPNext.

| Direction | What | How |
| --- | --- | --- |
| FoaMES reads ERPNext | Resolve External References (Item, UOM, Batch, Serial No, Work Order, Operation, Warehouse, Stock Entry, Job Card, BOM, Routing, Workstation) with their details; list open Work Orders and Job Cards | `frappe.db` reads of ERPNext's tables |
| FoaMES writes ERPNext | Stock Entries against a Work Order (transfer, manufacture, consumption), Job Card time logs, Work Order stop, resume and close | ERPNext's own whitelisted functions, through the **ERPNext Outbox** |
| Machines write ERPNext | A machine's good and scrap counts and its running time, rolled up to the Job Card it is working on | The machine's **Current Job Reference**, the scheduler and the outbox |
| ERPNext tells FoaMES | A mapped record was saved, renamed or deleted | `doc_events` hooks that refresh the matching External Reference |
| The floor | Open Job Cards and Work Orders per machine, and a rule for a machine running without one | `foames_floor_snapshot_extensions` and `foames_suggestion_rules` |

### Setup

1. Install ERPNext and FoaMES on the same site. Set **Default ERP System** in FoaMES Settings to
   `ERPNext` if new references should point at ERPNext by default.
2. Open **ERPNext Adapter Settings**:
   - **Enable Postings to ERPNext** to let the scheduler perform queued postings. Until it is on,
     postings queue up and wait; nothing is lost.
   - **Pause the Outbox** to stop performing postings for a while, for example during a stock take.
   - **Submit Job Cards When Complete** is the default for time-log postings that do not say.
   - **Roll Up Machine Counts to Job Cards** queues each machine's counts and run time to the Job
     Card named by its Current Job Reference; see [Rolling machine counts up](#rolling-machine-counts-up-to-job-cards).
   - **Show Job Cards on the Floor** and **Look Ahead (days)** control the floor snapshot section.
   - **Refresh Unresolved References Daily** re-checks references that are Unverified or Missing.
3. Point each Machine at its ERPNext Workstation through **Workstation Reference** (an External
   Reference of type Workstation). That is what ties live machine state to ERPNext's job list.

### Reading ERPNext

`External Reference.resolve()` and the adapter's `resolve(reference_type, external_id)` return
the record's label and a `data` dict. For the manufacturing types the dict carries what a shop-floor
screen or an agent needs without a second call:

| Reference type | `data` holds |
| --- | --- |
| Work Order | item, BOM, qty, produced qty, transferred qty, status, warehouses, dates, `operations` (operation, workstation, sequence, time, completed qty, status) and `required_items` |
| Job Card | work order, operation, workstation, for quantity, completed quantity, status, sequence, dates and `time_logs` |
| Bill of Materials | item, quantity, UOM, active and default flags, routing, `items` and `operations` |
| Routing | name, disabled flag and `operations` |
| Stock Movement | purpose, type, work order, job card, finished quantity, warehouses, posting date |
| Workstation | name, type, status, capacity, warehouse |

Field names follow ERPNext; a column that does not exist on the installed release is left out
rather than failing.

Whitelisted reads (roles FoaMES Operator, Engineer, Quality, Integration or System Manager):

| Method | Returns |
| --- | --- |
| `foames.foames_adapters.erpnext.api.get_work_order(name)` | The Work Order's `data` dict |
| `foames.foames_adapters.erpnext.api.list_open_work_orders(workstation=None, limit=100)` | Submitted Work Orders that are Not Started, In Process or waiting on reserved stock |
| `foames.foames_adapters.erpnext.api.list_open_job_cards(workstation=None, machine=None, limit=200)` | Job Cards that are still open: drafts, and submitted ones still Work In Progress; optionally for the workstation a Machine points at |
| `foames.foames_adapters.erpnext.api.get_operations()` | The outbox operations and the payload keys each one takes |

### The outbox

Every write to ERPNext is queued as an **ERPNext Outbox** record and performed by the scheduler
(`scheduler_events["all"]`, so within a few minutes). Code queues a posting with:

```python
from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue

enqueue(
	"Manufacture",
	{"work_order": "MFG-WO-2026-00012", "qty": 40},
	idempotency_key="MFG-WO-2026-00012:shift-2:manufacture",
	sequence_group="MFG-WO-2026-00012",
)
```

or over HTTP as `POST /api/method/foames.foames_adapters.erpnext.api.post` with the same
arguments (`payload` may be a JSON string). The call needs create permission on ERPNext Outbox
(roles FoaMES Engineer and FoaMES Integration have it) and returns the outbox record's name and
status; `get_posting(name)` reports progress.

| Operation | Payload | What ERPNext does |
| --- | --- | --- |
| `Material Transfer for Manufacture` | `work_order`, optional `qty`, `posting_date`, `posting_time`, `remarks`, `submit` | Builds the Stock Entry the Work Order form's **Start** button builds (source warehouse to WIP), inserts and submits it |
| `Manufacture` | same | The **Finish** entry: consumes from WIP and receives the finished good, updating the Work Order's produced quantity and status |
| `Material Consumption for Manufacture` | same | Consumes materials without receiving finished goods (needs **Allow Continuous Material Consumption** in Manufacturing Settings) |
| `Job Card Time Log` | `job_card`, `start_time` and/or `complete_time`, optional `completed_qty`, `employees`, `submit` | `start_time` opens a time log row and `complete_time` closes the open one, both through `make_time_log`, which validates the operation sequence and updates the Job Card's status; a posting with both times is applied as a start followed by a completion, and a completion with no open row is rejected. The Job Card's totals are recomputed, and with `submit` (or the settings default) it is submitted once its completed quantity reaches its for quantity |
| `Job Card Production Log` | `job_card`, `from_time`, `to_time`, optional `completed_qty`, `process_loss_qty`, `run_intervals` (list of `[from, to]`), `remarks`, `submit` | Appends one time log per run interval (or one for the whole window) with `completed_qty` on the last, adds `process_loss_qty` to the Job Card's process loss where ERPNext keeps the value (recent versions derive the field as planned minus completed, so the scrap is also written into the remarks), and saves through the Job Card's own validation (overlaps, totals); a Job Card that is no longer a draft rejects it; with `submit` (or the settings default) the Job Card is submitted once completed plus loss reaches its for quantity |
| `Work Order Status` | `work_order`, `status` = `Stopped`, `Resumed` or `Closed` | `stop_unstop` or `close_work_order`; already being in that state counts as done |

`qty` defaults to the Work Order's remaining quantity, as it does in the form. `submit` defaults
to true for Stock Entries; pass `false` to leave a draft for review.

#### Idempotency, order and errors

- **One record per idempotency key.** Queuing the same key again returns the first record, so a
  caller can retry freely. Name the key after the business event
  (`<work order>:<operation>:complete`), never after the attempt.
- **A marker in the document.** Every Stock Entry FoaMES creates carries `FOAMES-<16 hex>` (a hash
  of the key) at the start of its remarks, and every Job Card touched gets the marker appended to
  its remarks. Before performing a posting the outbox looks for the marker and, if the document is
  already there, records it instead of posting again.
- **One transaction.** ERPNext runs on the same database, so the ERPNext document and the outbox
  record's update are committed together. A rejected posting is rolled back whole; nothing half
  done is left in ERPNext.
- **Sequence groups.** Postings with the same `sequence_group` (use the Work Order) are performed
  strictly in queue order. A failed one holds the later ones until it is requeued or cancelled.
- **Retry or Failed.** Lock and timing conflicts (`QueryDeadlockError`, `TimestampMismatchError`,
  `DocumentLockedError`, driver errors) are retried with backoff from 1 minute, doubling to 6 hours,
  10 attempts. A `ValidationError` or `PermissionError` from ERPNext (short stock, an over-production
  limit, a closed Work Order, a missing permission) marks the posting **Failed** with ERPNext's
  message in **Last Error**. Fix the cause, then **Requeue** on the form; **Cancel Posting** drops
  it and unblocks its group.
- **Who posts.** A posting runs as the user who queued it, so ERPNext's permissions on Stock Entry,
  Job Card and Work Order apply to that user. Postings queued by the scheduler run as Administrator.
- **Monitoring.** Filter the ERPNext Outbox list by status. Retries also leave an Error Log entry.

### Rolling machine counts up to Job Cards

A Machine says which job it is working on through **Current Job Reference**, an External Reference
of type Job Card (set on the form, through
`foames.foames_mes.api.set_current_job(machine, reference, at=None)`, or by an agent). **Current
Job Since** is set with it. The core keeps only that reference; everything ERPNext-specific is in
the adapter.

With **Enable Postings** and **Roll Up Machine Counts to Job Cards** on, every ten minutes the
adapter takes, for each machine with a current ERPNext Job Card, the window since its last roll-up
(or since the job was set), sums the Count deltas of the good counters (`good`, `count`, `total`,
`parts`) and the scrap counters (`scrap`, `reject`, `bad`, `ng`), and finds the stretches the
machine reported Running. If any of the three is more than zero it queues one
`Job Card Production Log` posting for the window, with the Job Card as the sequence group and the
Machine as the posting's reference. The window's end is its idempotency key, so a repeated run
queues nothing new, and the newest posting for the machine and card tells the next run where to
start. An idle window queues nothing.

When the machine's current job changes (the `foames_machine_job_changed` hook), the job that
ended is rolled up to the moment of the change first, so counts never land on the wrong card.

On the Job Card each run stretch becomes a time log (the good quantity rides on the last one),
and the scrap goes to **Process Loss Qty** where the installed ERPNext keeps it (recent versions
derive that field as planned minus completed); the scrap is also noted in the remarks. The Job
Card validates the rows as if they were entered by hand: a stretch overlapping another Job Card's
time log on a workstation at capacity is rejected and the posting goes to **Failed** with ERPNext's
message. Because the sequence group is the Job Card, later windows wait behind it until it is
requeued or cancelled, and no window is skipped.

The floor snapshot shows the current job on each machine (`current_job`, with `open` and
`docstatus` from ERPNext) and marks the matching entry of `job_cards` with `current: true`. The
rule `current_job_card_not_open` raises a suggestion for a machine whose current Job Card is
submitted, cancelled or gone, since its counts can no longer be rolled up.

### Keeping references current

For every ERPNext DocType the adapter maps, hooks on `on_update`, `on_update_after_submit`,
`on_trash` and `after_rename` keep the matching External Reference's label and status current:
a saved record is Resolved with a fresh label, a deleted record leaves its reference Missing (the
FoaMES records that point at it are not touched), and a renamed record is followed to its new name.
A daily task re-checks references that are still Unverified or Missing. Both are no-ops on a site
without ERPNext.

### The floor

With **Show Job Cards on the Floor** on, the floor snapshot gains, per machine, `workstation` and
`job_cards` (the open Job Cards on that workstation whose expected start is within **Look Ahead
(days)** of now, or that have no expected start), and an `erp` section
with the open Work Orders, the Job Card count and the machines that have no workstation reference.
The rule `running_without_job_card` raises an Agent Suggestion when a machine reports Running
while its workstation has no open Job Card. External agents read the same snapshot through
`foames.foames_mes.api.get_floor_snapshot`; see [agents/floor-agent.md](agents/floor-agent.md).

### For agents

An agent that drives ERPNext through FoaMES does this, in order:

1. `list_open_job_cards(machine=...)` or `get_work_order(name)` to see what is planned.
2. `post("Material Transfer for Manufacture", {...})` when a job starts, with the Work Order as
   `sequence_group`.
3. `post("Job Card Time Log", {"job_card": ..., "start_time": ...})` at the start and
   `{"job_card": ..., "complete_time": ..., "completed_qty": ..., "submit": true}` at the end.
4. `post("Manufacture", {"work_order": ..., "qty": ...})` for the finished quantity.
5. `get_posting(name)` to confirm each posting reached **Posted**, and read **Last Error** when one
   is **Failed** before deciding whether to change the payload and requeue.

Use idempotency keys an agent can reconstruct from the event, so a retried conversation never
posts twice.

### Tests

`foames/foames_adapters/erpnext/test_postings.py` and `test_production.py` cover the rules and
the roll-up arithmetic without a site; `foames_mes/doctype/machine/test_machine.py` covers the
machine's current job on any site. The outbox's
queue behaviour runs on any Frappe site (`doctype/erpnext_outbox/test_erpnext_outbox.py`). The
end-to-end tests in `test_erpnext_integration.py` need ERPNext on the site; they create a company
`FoaMES Test Co` with a raw material, a finished good with a one-operation BOM and a workstation,
and they skip when ERPNext is not installed. CI runs them in the "Frappe v16 + ERPNext" job.

## Running without an ERP

Leave **Default ERP System** empty. Machines, events, downtime, OEE, the Floor View and suggestions work without any reference. An External Reference cannot be saved without an ERP System, because there is nothing to resolve it against, so simply do not create any. When an ERP arrives later, set the default and start adding references; nothing else changes.

## Writing an adapter for another ERP

An adapter is a Python class that another Frappe app registers through the `foames_erp_adapters` hook. FoaMES ships two: `foames.foames_adapters.erpnext.ERPNextAdapter` and `foames.foames_adapters.s4hana.adapter.S4HANAAdapter`.

```python
# myapp/adapters/acme_erp.py
import frappe

from foames.foames_adapters.base import ERPAdapter, ResolvedReference


class AcmeERPAdapter(ERPAdapter):
	key = "AcmeERP"          # stored on External Reference.erp_system
	label = "Acme ERP"       # shown to users
	reference_map = {        # kernel reference type -> the ERP's own record type
		"Item": "material",
		"Work Order": "production_order",
		"Location": "storage_location",
	}

	def is_available(self) -> bool:
		# True when the ERP can be reached from this site: a setting is filled in, a connection works.
		return bool(frappe.db.get_single_value("Acme ERP Settings", "enabled"))

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		# erp_type is reference_map[reference_type]. Return None when the record does not exist.
		record = acme_client().get(erp_type, external_id)
		if not record:
			return None
		return ResolvedReference(
			reference_type=reference_type,
			external_id=record["id"],
			label=record["description"],
			data={"type": erp_type},
		)
```

```python
# myapp/hooks.py
foames_erp_adapters = ["myapp.adapters.acme_erp.AcmeERPAdapter"]
```

The contract, from `foames/foames_adapters/base.py`:

- `key`, `label` and `reference_map` are class attributes. `reference_map` may also be a property when the mapping depends on settings, as the S/4HANA adapter does.
- `is_available()` says whether the ERP can be reached now. The core calls it before every lookup and treats `False` as "leave the reference Unverified", never as an error.
- `fetch(erp_type, reference_type, external_id)` returns a `ResolvedReference` or `None`. Raise `foames.foames_adapters.base.AdapterUnavailable` for a transient failure (timeout, authentication problem) so the save still goes through, and `AdapterError` for a real failure that should be shown to the user.
- `resolve(reference_type, external_id)` is implemented on the base class and is what the core calls. It checks support and availability, then calls `fetch`. Do not override it.
- Adapters are instantiated on every lookup, so keep the constructor cheap and cache connections elsewhere (for example in `frappe.cache` or a module-level client).

Once registered, the adapter appears in `get_available_erp_systems`, its key is accepted in **ERP System** and **Default ERP System**, and External References of its supported types resolve through it. Nothing in the core needs to change.

Keep two rules when you write one:

1. Resolve by reading. Writing to the ERP belongs in explicit, idempotent postings, as the S/4HANA outbox does, not inside `fetch`.
2. Store credentials in Password fields of a Settings DocType, never in code or site config.
