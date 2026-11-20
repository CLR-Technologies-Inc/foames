# Onshape

FoaMES connects to [Onshape](https://www.onshape.com/) CAD/PDM as a **read-only CAD source**: engineers can point an Item, Work Order or Job Card at the Onshape document, part, assembly or drawing it was built from, pinned to an immutable version or microversion, and trace production records back to the exact design revision used.

Onshape stays the design source of truth. FoaMES stores links and metadata, never geometry, and never writes to Onshape.

## What ships

| Piece | Where |
| --- | --- |
| Connector (signatures, model, GET-only client, fake transport) | `foames/foames_adapters/onshape/` |
| Settings (single DocType) | **Onshape Settings** |
| Link records | **Onshape CAD Reference** |
| Desk/API reads and linking | `foames.foames_adapters.onshape.api` |

Agent-facing rules: [foames/foames_adapters/onshape/AGENTS.md](../../../foames/foames_adapters/onshape/AGENTS.md).

## Setup

1. In Onshape, create an API key at the developer portal (dev-portal.onshape.com) with **read** scopes for documents. Copy the access key and secret key — the secret is shown once.
2. In FoaMES, open **Onshape Settings** (FoaMES Adapters module):
   - **Enabled** on.
   - **Base URL**: `https://cad.onshape.com`, or the Enterprise tenant URL for enterprise deployments.
   - **Access Key** and **Secret Key**: the API key pair. The secret is stored in a Password field.
   - Optionally restrict **Allowed Documents** to one document id per line; empty allows any document the key can read.
3. Use **Test Connection** on the settings document. It signs one request and reads the key's owner — proving URL, credentials and reachability without touching document data.

Authentication is Onshape's request-signature scheme (`Authorization: On <access key>:HmacSHA256:…`). Basic API-key auth is deliberately not supported — Onshape documents it for local testing only. OAuth2 is the path for multi-user or App Store distribution and is a follow-up.

## Linking a design to a FoaMES record

From code or a client of the API:

```python
frappe.call(
    "foames.foames_adapters.onshape.api.link_reference",
    target_doctype="Work Order",
    target_name="MFG-WO-2026-0001",
    document_id="<onshape did>",
    wvm_type="v",          # or "m" for a microversion; "w" for unreleased workspace
    wvm_id="<version id>",
    element_id="<eid>",    # optional: part studio, assembly or drawing
    kind="Part",
    title="Bracket, rev C",
)
```

`get_references(target_doctype, target_name)` returns the panel data for a record: title, kind, revision label, pinned flag, source URL, sync status and last-synced time.

## Revision awareness

- `w` (workspace) is **mutable** and always displays as *Unreleased workspace*.
- `v` (version) and `m` (microversion) are **immutable**; the reference is marked **Pinned** automatically.
- `Onshape CAD Reference.refresh` re-reads the document. When a newer version exists, a pinned reference becomes **Superseded** — the baseline is never silently re-pointed; a person decides whether to re-link.
- Unreachable documents become **Inaccessible**; failed refreshes become **Stale**. Existing links and their provenance are kept either way.

## Limits and errors

- Read-only: only GET requests are issued. There is no write path, and none may be added without the write gate (`docs/read-only-mode.md`).
- 401/403 (bad or revoked key, missing scope) fails immediately; 429 honours `Retry-After` with backoff; 402 means the account's annual API quota is exhausted.
- `allowed_documents` bounds what can be linked; assembly/BOM structure is only as complete as the account's plan exposes — an Onshape assembly is geometric structure, not an approved manufacturing BOM.

## Documentation

- [Onshape REST API quick start](https://onshape-public.github.io/docs/api-intro/quickstart/)
- [API key authentication and request signatures](https://onshape-public.github.io/docs/auth/apikeys/)
- [API limits and usage terms](https://onshape-public.github.io/docs/auth/limits/)
- [Document / version model](https://onshape-public.github.io/docs/api-intro/)
