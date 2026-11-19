# AGENTS.md: Onshape

Read this when you work in `foames/foames_adapters/onshape/` or on the Onshape DocTypes under `foames/foames_adapters/doctype/onshape_*`. The rules that hold for every adapter are in [../AGENTS.md](../AGENTS.md); the project-wide rules are in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/onshape/](../../../docs/vendors/onshape/README.md).

## What it is

Onshape CAD/PDM, reached over its REST API as a **CAD source, not an ERP**. This package deliberately does not implement `ERPAdapter` and is not registered in `foames_erp_adapters`: CAD objects are not ERP records, and nothing here resolves `External Reference`s. CAD links live in the `Onshape CAD Reference` DocType (`link_doctype` + `link_name` + the Onshape ids), which any FoaMES record can be pointed at through `foames.foames_adapters.onshape.api.link_reference`.

Read-only in v1: the client refuses every method but GET. No geometry, no writes, no release actions.

## Package map

Modules that import nothing from Frappe, tested without a site:

- `auth.py` — the request-signature scheme: `On-Nonce`, `Date` and `Authorization: On <access key>:HmacSHA256:<base64>` over the lowercased `method\nnonce\ndate\ncontent-type\npath\nquery` string. Basic auth is not implemented on purpose (Onshape documents it for local testing only).
- `model.py` — `CadReference` (kind, document id, wvm selector `w`/`v`/`m`, element/part ids, canonical URL), the pinned-vs-unreleased rule, Onshape URL parsing and BOM-row extraction that keeps provenance.
- `client.py` — `OnshapeClient`, a GET-only client with an injected transport, error classes (`OnshapeAuthError`, `OnshapeRateLimited`, `OnshapeQuotaExceeded`, `OnshapeUnavailable`) and bounded retries that honour `Retry-After`.
- `fake.py` — the scripted stand-in the tests use.

Frappe side: `api.py` (whitelisted reads and `link_reference`), `doctype/onshape_settings` (single: enabled, base URL, access key, secret key Password field, timeout, allowed-documents scope) and `doctype/onshape_cad_reference` (the link record; `pinned` is derived from `wvm_type`, `refresh` re-reads the document and marks a moved pinned reference `Superseded` rather than re-pointing it).

## Rules specific to this connector

- **Secrets** live in the `secret_key` Password field of Onshape Settings, read with `get_password`. The access key is not secret but is still never logged.
- **Scope**: `allowed_documents` limits which document ids can be linked or refreshed; enforce it in `api.py` and in `Onshape CAD Reference.refresh`, not only in the UI.
- **Pinning**: `w` is mutable workspace state and must always present as "Unreleased workspace"; `v`/`m` are immutable. A design change must surface as `Superseded`/`Stale`, never as a silent re-point of a pinned reference.
- **Rate limits and quota**: 429 honours `Retry-After` with the normal backoff as fallback; 402 (annual quota) is permanent for the run; 401/403 stop immediately. Do not add retry storms.
- **BOM caution**: an Onshape assembly is geometric structure, not an approved manufacturing BOM. `model.parse_bom_rows` keeps source ids so a later reconciliation can tell them apart; do not post rows to an ERP.
- Everything in this folder is written from Onshape's public documentation. Do not add Onshape SDKs, generated API metadata or payloads copied from material behind a customer login.

## Tests

`test_onshape.py` covers signatures (cross-checked against an independent implementation of the documented scheme), the model, error mapping and retries against `fake.py`. It runs under `bench --site <site> run-tests --app foames --module foames.foames_adapters.onshape.test_onshape`. The DocType controllers have no site-free tests; exercise them through the API methods on a test site.
