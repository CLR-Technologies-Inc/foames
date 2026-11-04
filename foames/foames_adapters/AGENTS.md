# AGENTS.md: the adapter layer

Read this when you work anywhere under `foames/foames_adapters/`. It covers what is true for every adapter. What is true for one vendor is in that vendor's own `AGENTS.md`, in its subpackage, and nowhere above this folder. The project-wide rules are in the root [AGENTS.md](../../AGENTS.md).

## Discover, do not assume

This layer is open-ended: a site can have any number of adapters, bundled or registered by other apps. Do not work from a list in a document. Find out what is there:

- `ls foames/foames_adapters/`: each vendor subpackage is a directory with its own `AGENTS.md`. Read the one for the vendor you touch before you change anything in it.
- `frappe.get_hooks("foames_erp_adapters")`: the dotted paths of the registered adapter classes, bundled or not.
- `foames.foames_adapters.get_available_erp_systems` (whitelisted, logged-in users): every registered adapter with its key, label and whether its ERP is reachable from this site. Use it to map a running installation, not to infer what the code supports.
- `docs/vendors/<vendor>/`: the human guide for that vendor, and [docs/adapters.md](../../docs/adapters.md) for what is vendor-neutral.

Files that are not in a vendor's folder must not name a vendor, except `hooks.py` (which registers what is bundled) and tests of the registry.

## The contract

`base.py` holds `ERPAdapter`, `ResolvedReference`, `REFERENCE_TYPES` and the error classes (`AdapterError`, `AdapterUnavailable`, `UnsupportedReferenceType`). An adapter sets `key`, `label` and `reference_map` (a class attribute, or a property when it depends on settings), and implements `is_available()` and `fetch()`. `resolve()` is on the base class; do not override it. The registry functions (`get_adapters`, `get_adapter`, `get_available_erp_systems`) are in `__init__.py`. The full contract with an example adapter is in [docs/adapters.md](../../docs/adapters.md#writing-an-adapter-for-another-erp).

## Rules for every adapter

1. **No Link field to an ERP DocType, and no import of an ERP's package at module level.** Store an `External Reference`; resolve it in the adapter. The core must install and pass its tests on a plain Frappe site. If an adapter needs the ERP's code, reach it with `frappe.get_attr` after checking `is_available()`.
2. **Reading and writing are separate.** `fetch` reads. Writing to an ERP is an explicit, idempotent posting that a person configured, never a side effect of resolving a reference. An adapter may suggest (an `Agent Suggestion` through the `foames_suggestion_rules` hook) but does not change machine state or write tags.
3. **Postings are idempotent and sequenced.** Any new write path follows the existing outbox implementations: an idempotency key per business event; a marker written into the created document so a resend can first check whether it exists; a check before resending after an unclear answer; exponential backoff with a cap; and strict order within a sequence group. A posting that is not `Posted` or `Cancelled`, `Failed` included, holds back every later posting of its group until it is requeued or cancelled.
4. **Classify errors.** A rejection is `Failed` and needs a person; a transient error is retried. Unknown errors are retried, with the attempt cap as the backstop.
5. **Secrets live in Password fields** of the adapter's Settings DocType, read with `get_password`. Never in code, hooks or site config, never logged.
6. **Keep arithmetic, parsing and protocol code pure.** Payload building, retry rules, roll-up arithmetic and wire-format parsing import nothing from Frappe, so a unit test needs no site. The Frappe modules around them stay thin. Each vendor's `AGENTS.md` lists which of its modules are pure.
7. **Register through the hook.** `foames_erp_adapters` in `hooks.py` for a bundled adapter, in the other app's `hooks.py` for one that ships elsewhere. An adapter should report `is_available() == False` when its ERP is absent or not configured; the core treats that as "leave the reference Unverified", not as an error.

## Adding a reference type

Add the kernel type to `REFERENCE_TYPES` in `base.py` together with the Select options on `External Reference` and on every adapter mapping DocType that lists reference types (each vendor's `AGENTS.md` names its own). Then map the new type in each adapter that supports it. An adapter that does not support a type must answer `supports() == False`, not guess.

## Hooks an adapter may use

Adapters use the same extension points as any app; see the root `AGENTS.md` for the list: `foames_machine_event_handlers`, `foames_machine_job_changed`, `foames_machine_state_changed`, `foames_floor_snapshot_extensions` and `foames_suggestion_rules`. `machine_window.py` reads what a machine did in a window (counter totals, carried-in state, state changes) for the adapters that roll machine data up to an ERP job. An adapter that needs its own hook (for example for an inbound message type) declares and documents it in its own `AGENTS.md`, not in the root file.

## Adding a vendor

1. A subpackage `foames/foames_adapters/<vendor>/` with an adapter class registered as above, and its own `AGENTS.md` that states: what the adapter talks to, its package map, which modules are pure, its Settings and outbox DocTypes, its hooks, entry points and HTTP methods, how to add a reference type to it, how its tests run, and any rule specific to that vendor (licensing, forbidden dependencies, API metadata).
2. A guide at `docs/vendors/<vendor>/README.md` and a row in [docs/vendors/README.md](../../docs/vendors/README.md).
3. Tests that need no ERP, using a fake transport for a remote system; tests that do need the ERP skip when it is not installed.
4. `sbom/curated.json` when the adapter adds a connected service, cryptography or a secret (see the root `AGENTS.md`).
5. No change to the root `AGENTS.md`, `README.md` or the core docs beyond what the hooks and the registry already generalise.

## Reports, workspace and dashboards in this layer

`report/`, `workspace/`, `number_card/` and `dashboard_chart/` hold the Integration workspace, which is shared by all adapters. Check how a report reads each adapter's outbox DocType before you add a vendor, and keep anything specific to one vendor's DocTypes documented in that vendor's `AGENTS.md`. [docs/dashboards.md](../../docs/dashboards.md) lists the cards, charts and reports.
