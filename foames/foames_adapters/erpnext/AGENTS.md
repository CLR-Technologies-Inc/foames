# AGENTS.md: the ERPNext adapter

Read this when you work in `foames/foames_adapters/erpnext/` or on the ERPNext DocTypes under `foames/foames_adapters/doctype/`. The rules that hold for every adapter are in [../AGENTS.md](../AGENTS.md); the project-wide rules are in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/erpnext/](../../../docs/vendors/erpnext/README.md).

## What it is

A same-site adapter, registered under the key `ERPNext` (`ERPNextAdapter` in `__init__.py`). It is available when the `erpnext` app is installed on the site (`erpnext_installed()`), checked at run time and not at install time. It reads ERPNext's tables directly, so it needs no credentials, and it writes through ERPNext's own documents and whitelisted functions, so ERPNext's validation applies.

## Rules specific to this adapter

- **Nothing here imports from `erpnext`.** It reaches ERPNext through `frappe.get_doc`, `frappe.db` and `frappe.get_attr("erpnext...")` after `erpnext_installed()` is true, and the module-level code must load on a plain Frappe site. The `doc_events` entries in `hooks.py` name ERPNext DocTypes that do not exist on such a site; the handlers check the adapter is available before they touch anything.
- **A posting is performed as the user who queued it**, so ERPNext's own permission checks on Stock Entry, Job Card and Work Order apply to that user, not to the scheduler.
- **Everything that writes to ERPNext is off until a person enables it** in ERPNext Adapter Settings: `enable_postings` (with `outbox_paused` to hold the queue), `roll_up_counts_to_job_cards`, `inspect_job_cards_from_measurements` (with `inspection_delay_minutes`, default 5, to wait for late readings), `sync_machine_state_to_workstations`, `post_downtime_to_erpnext` and `submit_job_cards_when_complete` all default to 0. `follow_job_cards_started_in_erpnext` also defaults to 0; it writes only FoaMES Machines (their current job), never ERPNext. Keep new switches that write defaulting off. Reading is the exception: `show_job_cards_on_floor` and `refresh_references_daily` default on.

## Package map

Modules that import nothing from Frappe, tested without a site: `postings.py` (the outbox rules: operations, idempotency marker, error classification, retry) and `production.py` (the roll-up arithmetic).

Frappe side:

| Module | Holds |
| --- | --- |
| `__init__.py` | `ERPNextAdapter`, `ERPNEXT_DOCTYPES` (kernel reference type to ERPNext DocType and label field), `REFERENCE_TYPES_BY_DOCTYPE` |
| `details.py` | What is read for each reference type (Work Order operations, BOM items, Job Card time logs) |
| `executor.py` | Performs a posting against ERPNext |
| `sync.py` | ERPNext document events that keep External References current |
| `floor.py` | Job Cards and Work Orders in the floor snapshot, and a suggestion rule built on them |
| `rollup.py` | Rolls each machine's counts and run time up to the Job Card it is working on |
| `workstation.py` | Shows each machine's state on its ERPNext Workstation |
| `downtime.py` | Posts closed Downtime Records as Downtime Entries |
| `quality.py` | Quality Inspections from what the floor measured, including the inspection queued when a machine's job ends (`inspect_job_card`) |
| `follow.py` | Machines follow the Job Cards people start, complete, cancel or delete in ERPNext |
| `api.py` | Whitelisted endpoints |
| `fixtures.py` | Test fixtures for a site that has ERPNext (a company, a raw material with stock, a finished good with a one-operation BOM, a workstation, a Quality Inspection Template) |

DocTypes in `foames/foames_adapters/doctype/`: `erpnext_adapter_settings`, `erpnext_outbox`.

## Hooks, entry points and endpoints

| Item | Detail |
| --- | --- |
| `doc_events` in `hooks.py` | ERPNext document events call `sync.on_update`, `on_update_after_submit`, `on_trash` and `after_rename` for the mapped DocTypes; `Stock Entry.on_submit` calls `sync.on_submit` (serial numbers of a draft Manufacture entry); Job Card `on_change` calls `follow.on_job_card_change` (it runs after ERPNext's `db_set` too, which is how Start Job marks a card Work In Progress on v16 without saving it) and `on_trash` also calls `follow.on_job_card_trash`; `Downtime Record.on_update` calls `downtime.on_update`. |
| Core hooks it uses | `foames_floor_snapshot_extensions` (`floor.extend_snapshot`, `rollup.mark_current_job_cards`), `foames_suggestion_rules` (`floor.running_without_job_card`, `rollup.current_job_card_not_open`), `foames_machine_job_changed` (`rollup.on_job_changed`, `quality.on_job_changed`) and `foames_machine_state_changed` (`workstation.on_state_changed`). Registered in `hooks.py`. |
| `foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox.enqueue(...)` / `process_outbox()` | Queue a posting; perform due postings (scheduler). |
| Scheduler (in `hooks.py`) | `erpnext_outbox.process_outbox`, and `erpnext.rollup.roll_up_all`; each does nothing unless enabled in ERPNext Adapter Settings. |
| `foames.foames_adapters.erpnext.api.*` | Reads (`get_operations`, `get_work_order`, `list_open_work_orders`, `list_open_job_cards`, `get_posting`), `post` (POST, needs create on ERPNext Outbox), `post_inspection_from_measurements` (POST, needs create on ERPNext Outbox and read on Machine Event), `process_outbox_now` (POST, System Manager or FoaMES Engineer). Reads check the caller's role; the list and the payload shapes are in the guide. |

## Adding a reference type

Add a row to `ERPNEXT_DOCTYPES` in `__init__.py` (kernel type, ERPNext DocType, label field) and cover it in `details.py` if it needs more than its label; `sync.py` and `REFERENCE_TYPES_BY_DOCTYPE` derive from the same table. A new *kernel* reference type is added to `REFERENCE_TYPES` and the External Reference Select options first (see [../AGENTS.md](../AGENTS.md)).

## Adding a posting operation

Add the operation to `postings.py` first, with its payload rules and a pure test in `test_postings.py`, then the performer in `executor.py`, then an end-to-end test in `test_erpnext_integration.py`. Keep the marker in the created document so a replay finds it instead of creating a second one.

## Tests

- Pure: `test_postings.py` and `test_production.py` need no site.
- Outbox queue behaviour runs on any Frappe site (`doctype/erpnext_outbox/test_erpnext_outbox.py`).
- End-to-end: `test_erpnext_integration.py` needs ERPNext on the site and skips otherwise. CI runs it in the "Frappe v16 + ERPNext" job; locally the Docker dev bench runs it with `ERPNEXT_BRANCH` set (see [docs/dev-bench.md](../../../docs/dev-bench.md)). The outbox commits after each posting, so these tests leave their Work Orders and Stock Entries in the `FoaMES Test Co` company.

Two things that have failed the ERPNext job and are easy to repeat:

- **A failed posting holds its sequence group.** The outbox treats any earlier posting that is not `Posted` or `Cancelled` as blocking, `Failed` included. A test that queues several deliberately failing postings for the same Job Card or Work Order must give each its own sequence group (or cancel the failed one), or the later ones stay `Queued` and never run.
- **Whitelisted methods type-check their arguments on Frappe v16 even when called from Python.** Pass strings, not `datetime` objects, to a function annotated `str`, as an HTTP caller would.
