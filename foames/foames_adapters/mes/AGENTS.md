# AGENTS.md: the shared MES and MOM adapter framework

Read this when you work in `foames/foames_adapters/mes/`, on MES Connection, MES Entity Mapping or MES Outbox, or on any vendor folder whose adapter subclasses `ProfileAdapter`. The rules that hold for every adapter are in [../AGENTS.md](../AGENTS.md); the project-wide rules are in the root [AGENTS.md](../../../AGENTS.md). The human guide for the framework is [docs/mes-adapters.md](../../../docs/mes-adapters.md); each system on it has its own page under [docs/vendors/](../../../docs/vendors/README.md).

This package is vendor-neutral. It holds what the systems built on it share; anything true of one system belongs in that system's folder (`profile.py`, its `AGENTS.md`, its guide). Find the systems on it by looking for `adapter.py` files that subclass `ProfileAdapter`, or by `ADAPTERS` in `test_profiles.py`, not from a list here.

## What it is

Many MES, MOM and frontline systems differ in how a caller logs in, how a record is addressed and how an answer is wrapped, but not in what FoaMES needs of them: resolve an External Reference, and queue a write that is never performed twice. So each system is a thin folder next to this one with a **profile** (a `Profile` from `profile.py`), and this package holds the machinery:

| Module | Pure | Holds |
| --- | --- | --- |
| `rest.py` | yes | A JSON REST client with the authentication styles these systems use: Basic, a static bearer token, an API key header, OAuth 2.0 client credentials. Transport injected. |
| `entities.py` | yes | How a kernel reference type maps to a resource: a path, a lookup style (Path, Query, OData filter, JSON filter), key fields and a label field. |
| `profile.py` | yes | The `Profile` dataclass and the operation definitions. |
| `outbox.py` | yes | The outbox rules: how an operation is kept from being performed twice (upsert, client reference, or manual check), retry and backoff. |
| `fake.py` | yes | A scripted stand-in for a system's HTTP interface, used by the tests. |
| `adapter.py` | no | `ProfileAdapter`, the Frappe side, reading one MES Connection per adapter key. |

Site records in `foames/foames_adapters/doctype/`: `mes_connection` (one per system, secrets in Password fields, with the child table `mes_entity_mapping`) and `mes_outbox`. No new DocType is needed for a new system.

## Rules for the framework and every profile

- **A profile ships a path only when the vendor publishes it as a stable public API.** Otherwise it says where the documentation is (`docs_url`, `notes`) and the site maps the type on its MES Connection. An unmapped reference type is refused when an External Reference is created; never guess a path.
- **No vendor code, SDK or API metadata in the repository.** Profiles are written from public documentation and product descriptions. Do not paste OpenAPI files, sample payloads or anything behind a customer login.
- **Every write is idempotent by one of three kinds**, chosen per posting: an **upsert** (a PUT, or `"idempotent": true`), a **client reference** (`reference_field`, `lookup_path`, optionally `lookup_query`: FoaMES writes a marker into a field the system keeps and searches for it before a resend), or **manual** (neither: an unclear answer stops the posting in Unknown with Needs Check, for a person to Mark Posted, Requeue or Cancel). Never resend a manual posting blind.
- **A system's quirks stay in its profile.** If a system needs something the framework does not have (a header, a token URL pattern, a site parameter), add a general field to `Profile` or `rest.py` and set it in that profile, so the next system can use it too.

## Hooks, entry points and endpoints

| Item | Detail |
| --- | --- |
| `foames.foames_adapters.doctype.mes_outbox.mes_outbox.enqueue(connection, operation, payload, idempotency_key, sequence_group=None, ...)` | Queue a write through a connection. Every profile has the `REST Request` operation: `method`, `path`, `body` and the idempotency fields above. |
| Document methods | `MES Connection.test_connection`, `MES Outbox.requeue`, `MES Outbox.mark_posted`, `MES Outbox.cancel_posting`. |
| Scheduler (in `hooks.py`) | `mes_outbox.process_outbox`. |
| Reports and workspace | ERP Outbox Health shows each MES Connection as its own adapter; the Integration workspace has MES Postings Failed / Waiting and MES Postings per Day. |

## Adding a system on this framework

1. A folder `foames/foames_adapters/<system>/` with `profile.py` (a `Profile`: key, label, vendor, product, `docs_url`, `base_url_hint`, `auth_methods`, `api_key_header`, `token_url_hint`, `site_label`, `headers`, `entities` only where published, `notes`), `adapter.py` (a `ProfileAdapter` subclass with `profile = PROFILE`), an `__init__.py` docstring, and an `AGENTS.md` like the existing ones.
2. Register the class in `foames_erp_adapters` in `hooks.py`, add its key to the Select on MES Connection, and add it to `ADAPTERS` in `test_profiles.py`. These three are the only places outside its folder that may name it.
3. A guide at `docs/vendors/<system>/README.md` (key, connection style, what the profile ships, the system notes), a row in `docs/vendors/README.md` and a row in the Integrations section of the root `README.md`. Do not add the system to `docs/mes-adapters.md`.
4. `sbom/curated.json` if it adds a connected service (see the root `AGENTS.md`).

## Adding a reference type

For one system: map it on its MES Connection, or add an `EntitySpec` to that system's `profile.py` only when the vendor publishes the path as a stable public API. A new *kernel* reference type also needs the Select options on MES Entity Mapping extended, together with `REFERENCE_TYPES` and External Reference (see [../AGENTS.md](../AGENTS.md)).

## Tests

`test_rest.py`, `test_entities.py`, `test_outbox_rules.py` and `test_profiles.py` cover the framework and every registered profile with `fake.py`, so no vendor system is needed; `doctype/mes_connection/` and `doctype/mes_outbox/` have their own tests. They run under `bench --site <site> run-tests --app foames` because the adapters package imports Frappe.
