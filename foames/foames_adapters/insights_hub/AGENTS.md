# AGENTS.md: the Siemens Insights Hub adapter (Opcenter Intelligence)

Read this when you work in `foames/foames_adapters/insights_hub/` or on the Insights Hub DocTypes under `foames/foames_adapters/doctype/`. The rules that hold for every adapter are in [../AGENTS.md](../AGENTS.md); the project-wide rules are in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/insights_hub/](../../../docs/vendors/insights_hub/README.md).

## What it is

A remote adapter, registered under the key `INSIGHTS_HUB` (`adapter.py`, class `InsightsHubAdapter`). Insights Hub (formerly MindSphere) is Siemens' industrial IoT platform; Opcenter Intelligence runs on it and reads production data from the platform's asset model, time series and events. The adapter works over HTTPS through the platform gateway:

- A Workstation or a Location resolves as an Insights Hub asset. The Opcenter Intelligence resources a site uses (materials, orders, operations, batches) are mapped in Insights Hub Settings against the published API reference.
- Machine production goes to Insights Hub as time series records on the machine's asset, and state changes as events, through the Insights Hub Outbox.

## Rules specific to this adapter

- **No Siemens code, SDK or API metadata in the repository.** The adapter talks to the released platform REST APIs only, with the Python standard library.
- **No guessed resource defaults.** `entities.py` defaults only Workstation and Location (to assets). Every other reference type is mapped by the site in Insights Hub Settings with the service path, resource, key and label fields from the Opcenter Intelligence API reference. Do not add a default you have not checked against that reference.
- **Credentials** are Password fields of Insights Hub Settings, read with `get_password`; `rest.py` supports both token flows the platform offers.
- The outbox follows the rules in [../AGENTS.md](../AGENTS.md): idempotency key, retries with backoff, and strict order within a sequence group, where a `Failed` posting holds the group until it is requeued or cancelled.

## Package map

Modules that import nothing from Frappe, tested without a site: `rest.py` (REST client, both token flows), `entities.py` (what each kernel reference type resolves to), `outbox.py` (operations, idempotency, retry rules), `production.py` (the roll-up arithmetic: machine data to time series and events) and `fake.py` (an in-memory stand-in for the platform, used by the tests).

Frappe side: `adapter.py` (the registered class) and `rollup.py` (rolls each machine's counts, running time and job up to time series on its asset).

DocTypes in `foames/foames_adapters/doctype/`: `insights_hub_settings` (with the child table `insights_hub_entity_mapping`) and `insights_hub_outbox`. The Integration workspace has its cards (Insights Hub Postings Failed / Waiting) and chart (Insights Hub Postings per Day); ERP Outbox Health reads its outbox.

## Hooks, entry points and endpoints

| Item | Detail |
| --- | --- |
| `foames.foames_adapters.doctype.insights_hub_outbox.insights_hub_outbox.enqueue(operation, payload, idempotency_key, sequence_group=None, ...)` | Queue a time series write or an event. |
| Document methods | `Insights Hub Settings.test_connection`, `Insights Hub Outbox.requeue`, `Insights Hub Outbox.cancel_posting`. |
| Scheduler (in `hooks.py`) | `insights_hub_outbox.process_outbox`, and `insights_hub.rollup.roll_up_all`; each does nothing unless the adapter is enabled. |
| Core hooks it uses | `foames_suggestion_rules` (`rollup.posting_rejected`), `foames_machine_job_changed` (`rollup.on_job_changed`) and `foames_machine_state_changed` (`rollup.on_state_changed`). Registered in `hooks.py`. |

## Adding a reference type

Map it in Insights Hub Settings (an Insights Hub Entity Mapping row) from the Opcenter Intelligence API reference. A new *kernel* reference type also needs the Select options on Insights Hub Entity Mapping extended, together with `REFERENCE_TYPES` and External Reference (see [../AGENTS.md](../AGENTS.md)).

## Tests

The tests use `fake.py`, so no tenant is needed: `test_rest.py`, `test_entities.py`, `test_outbox_rules.py` and `test_production.py` cover the pure modules, `test_adapter.py` the registered class, and `doctype/insights_hub_*/test_*.py` the Settings and the Outbox. They run under `bench --site <site> run-tests --app foames` because the adapters package imports Frappe.
