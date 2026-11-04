# AGENTS.md: the SAP S/4HANA adapter

Read this when you work in `foames/foames_adapters/s4hana/` or on the S4HANA DocTypes under `foames/foames_adapters/doctype/`. The rules that hold for every adapter are in [../AGENTS.md](../AGENTS.md); the project-wide rules are in the root [AGENTS.md](../../../AGENTS.md). The human guides are [docs/vendors/s4hana/](../../../docs/vendors/s4hana/README.md): the overview, [setup](../../../docs/vendors/s4hana/setup.md) (users, communication arrangements, OAuth) and [postings](../../../docs/vendors/s4hana/postings.md) (confirmations, goods movements, cancellations, reads, endpoints).

## What it is

A remote adapter, registered under the key `S4HANA` (`adapter.py`, class `S4HANAAdapter`). It is available when S4HANA Settings is enabled and has a base URL.

- References resolve over S/4HANA's released OData V2 APIs.
- Postings go through the S4HANA Outbox with idempotency keys, retries and per-order sequencing.
- Order, material and batch downloads arrive as IDocs over an XML HTTP port.
- Nothing uses RFC or the NetWeaver RFC SDK.

## Rules specific to this adapter

- **No SAP code, SAP API metadata or vendor SDK in the repository.** The adapter speaks released OData APIs and IDoc XML only. The entity defaults in `entities.py` are things to check against a system's `$metadata`, and are documented that way; do not paste metadata or sample payloads copied from SAP material.
- **The S4HANA Outbox is the reference implementation** of the idempotent, sequenced write path in [../AGENTS.md](../AGENTS.md): an idempotency key per business event, a marker in the created document, a check before resending after an unclear answer, exponential backoff, strict order within a sequence group (the order). A new write path in any adapter follows it; a new S/4HANA operation is added to `outbox.py` first.
- **Credentials** (Basic, or OAuth 2.0 client credentials) are Password fields of S4HANA Settings, read with `get_password`. The OAuth bearer token is held in memory only (`odata.py`). Never log either.
- **Licensing** of the APIs and of indirect use is the customer's to check; the guide carries a note for S/4HANA customers and a note on certification. Keep claims about either in that guide, not in code comments or other documents.

## Package map

Modules that import nothing from Frappe, tested without a site: `outbox.py` (operations, idempotency, retry rules), `odata.py` (a standard-library OData V2 client), `idoc.py` (IDoc parsing), `entities.py` (which entity each kernel reference type resolves to, and key handling), `production.py` (the roll-up arithmetic), `confirmations.py`, `goods_movements.py`, `orders.py` and `values.py` (payloads, reads and OData value encoding), `actions.py` (function imports that cancel a confirmation or reverse a material document), and `fake.py` (a scripted stand-in for S/4HANA's HTTP interface, used by the tests).

Frappe side: `adapter.py` (the registered class), `api.py` (whitelisted endpoints), `rollup.py` (rolls each machine's counts and run time up to the order operation it is working on, as partial confirmations).

DocTypes in `foames/foames_adapters/doctype/`: `s4hana_settings` (with the Entity Mapping child table `s4hana_entity_mapping`), `s4hana_outbox`, `s4hana_inbound_idoc`. Reports in `foames/foames_adapters/report/`: S4HANA Outbox Reconciliation, and ERP Outbox Health, which is shared with other adapters. A Job Card resolves as an order operation (`ORDER|OPERATION`, or `ORDER|SEQUENCE|OPERATION` outside the standard sequence) unless a site maps it in S4HANA Settings.

## Hooks, entry points and endpoints

| Item | Detail |
| --- | --- |
| Hook `foames_s4hana_idoc_handlers` | A dict of IDoc message type to a list of dotted paths. Each handler is called with `(inbound_doc, idoc, summary)` after the IDoc's External Reference is recorded, inside a savepoint: if a handler raises, its writes are rolled back and the IDoc is marked Failed with the error. |
| `foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox.enqueue(operation, payload, idempotency_key, sequence_group=None, ...)` | Queue a posting. |
| `foames.foames_adapters.s4hana.api.receive_idoc` (POST) | S/4HANA's XML HTTP port posts IDocs here. Needs create on S4HANA Inbound IDoc, which the FoaMES Integration role has; refuses when the adapter is not enabled. |
| `foames.foames_adapters.s4hana.api.*` | Whitelisted reads (orders, confirmations, goods movements, balance, routings, bills of material, work centers) and postings (`confirm_order`, `post_goods_receipt`, `post_goods_issue`, `post_transfer`, `post_scrap`, `cancel_confirmation`, `reverse_material_document`). Each checks its own permission; the list is in the postings guide. |
| Document methods | `S4HANA Settings.test_connection`, `S4HANA Outbox.requeue`, `S4HANA Outbox.cancel_posting`. |
| Scheduler (in `hooks.py`) | `s4hana_outbox.process_outbox` on every tick, and `s4hana.rollup.roll_up_all`; each returns at once unless the adapter is enabled. |
| Core hooks it uses | `foames_machine_job_changed` (`rollup.on_job_changed`) and `foames_suggestion_rules` (`rollup.confirmation_rejected`, for rejected confirmations). Registered in `hooks.py`. |

## Adding a reference type

Either map it in S4HANA Settings at run time (an Entity Mapping row), or add a default `EntitySpec` to `entities.py` with its service, entity set, key fields and label, and a test in `test_entities.py` (every default must round-trip its own key). A new *kernel* reference type also needs the Select options on S4HANA Entity Mapping extended, together with `REFERENCE_TYPES` and External Reference (see [../AGENTS.md](../AGENTS.md)).

## Tests

The tests use `fake.py`, an in-memory stand-in for the OData transport, so no SAP system is needed. They run under `bench --site <site> run-tests --app foames --module foames.foames_adapters.s4hana.test_s4hana` (and the other `test_*` modules in this folder and in `doctype/s4hana_*/`), because the adapters package imports Frappe. Test the pure modules first and the DocType classes second. The roll-up arithmetic is tested in `test_production.py` and its Frappe side in `test_rollup.py`.
