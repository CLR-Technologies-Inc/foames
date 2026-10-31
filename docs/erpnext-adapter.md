# ERPNext adapter

The ERPNext adapter connects FoaMES to an ERPNext installed on the same Frappe site. FoaMES itself
depends on the Frappe framework only: no FoaMES DocType links to an ERPNext DocType and nothing is
imported from ERPNext at module load. When ERPNext is present the adapter switches on by itself.

| Direction | What | How |
| --- | --- | --- |
| FoaMES reads ERPNext | Resolve External References (Item, UOM, Batch, Serial No, Work Order, Operation, Warehouse, Stock Entry, Job Card, BOM, Routing, Workstation) with their details; list open Work Orders and Job Cards | `frappe.db` reads of ERPNext's tables |
| FoaMES writes ERPNext | Stock Entries against a Work Order (transfer, manufacture, consumption), Job Card time logs, Work Order stop, resume and close | ERPNext's own whitelisted functions, through the **ERPNext Outbox** |
| ERPNext tells FoaMES | A mapped record was saved, renamed or deleted | `doc_events` hooks that refresh the matching External Reference |
| The floor | Open Job Cards and Work Orders per machine, and a rule for a machine running without one | `foames_floor_snapshot_extensions` and `foames_suggestion_rules` |

## Setup

1. Install ERPNext and FoaMES on the same site. Set **Default ERP System** in FoaMES Settings to
   `ERPNext` if new references should point at ERPNext by default.
2. Open **ERPNext Adapter Settings**:
   - **Enable Postings to ERPNext** to let the scheduler perform queued postings. Until it is on,
     postings queue up and wait; nothing is lost.
   - **Pause the Outbox** to stop performing postings for a while, for example during a stock take.
   - **Submit Job Cards When Complete** is the default for time-log postings that do not say.
   - **Show Job Cards on the Floor** and **Look Ahead (days)** control the floor snapshot section.
   - **Refresh Unresolved References Daily** re-checks references that are Unverified or Missing.
3. Point each Machine at its ERPNext Workstation through **Workstation Reference** (an External
   Reference of type Workstation). That is what ties live machine state to ERPNext's job list.

## Reading ERPNext

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

## The outbox

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
| `Work Order Status` | `work_order`, `status` = `Stopped`, `Resumed` or `Closed` | `stop_unstop` or `close_work_order`; already being in that state counts as done |

`qty` defaults to the Work Order's remaining quantity, as it does in the form. `submit` defaults
to true for Stock Entries; pass `false` to leave a draft for review.

### Idempotency, order and errors

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

## Keeping references current

For every ERPNext DocType the adapter maps, hooks on `on_update`, `on_update_after_submit`,
`on_trash` and `after_rename` keep the matching External Reference's label and status current:
a saved record is Resolved with a fresh label, a deleted record leaves its reference Missing (the
FoaMES records that point at it are not touched), and a renamed record is followed to its new name.
A daily task re-checks references that are still Unverified or Missing. Both are no-ops on a site
without ERPNext.

## The floor

With **Show Job Cards on the Floor** on, the floor snapshot gains, per machine, `workstation` and
`job_cards` (the open Job Cards on that workstation whose expected start is within **Look Ahead
(days)** of now, or that have no expected start), and an `erp` section
with the open Work Orders, the Job Card count and the machines that have no workstation reference.
The rule `running_without_job_card` raises an Agent Suggestion when a machine reports Running
while its workstation has no open Job Card. External agents read the same snapshot through
`foames.foames_mes.api.get_floor_snapshot`; see [agents/floor-agent.md](agents/floor-agent.md).

## For agents

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

## Tests

`foames/foames_adapters/erpnext/test_postings.py` covers the rules without a site. The outbox's
queue behaviour runs on any Frappe site (`doctype/erpnext_outbox/test_erpnext_outbox.py`). The
end-to-end tests in `test_erpnext_integration.py` need ERPNext on the site; they create a company
`FoaMES Test Co` with a raw material, a finished good with a one-operation BOM and a workstation,
and they skip when ERPNext is not installed. CI runs them in the "Frappe v16 + ERPNext" job.
