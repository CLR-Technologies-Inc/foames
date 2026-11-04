# The MES and MOM adapter framework

FoaMES is often not the only manufacturing system in a plant. An enterprise MES or MOM suite holds
the orders, materials, batches and equipment, or a frontline platform runs the operator apps, while
FoaMES reads the machines, computes OEE and raises suggestions. These adapters let FoaMES refer to the
records those systems own, and queue writes to them that are never performed twice. They are
registered through the same `foames_erp_adapters` hook as every other
adapters, so an External Reference can point at any of them.

Which systems have a profile, with each one's key and connection style, is listed in [vendors/](vendors/README.md); each has a page there with what is particular to it.

Each folder holds a **profile**: the key and label, where the vendor's public API documentation
lives, how the system authenticates, what the base URL looks like, the entity lookups documented well
enough to ship as defaults, and the operations the outbox offers. The machinery they share is in
`foames/foames_adapters/mes/`, and the site records are **MES Connection**, **MES Entity Mapping**
and **MES Outbox**.

## What is built in, and what you enter

The profiles were written from the vendors' public documentation and product descriptions, but they
could not be checked against the live API references while this version was built, so they follow one
rule: **a profile ships a path only when the vendor publishes it as a stable public API, and otherwise
says where to find it.** Each system's page under [vendors/](vendors/README.md) says what its profile ships and where the rest is documented.

Nothing is guessed on your behalf. An unmapped reference type is refused when an External Reference
is created, which is better than resolving against a path that does not exist.

## Setup checklist

| Step | Where | Done when |
| --- | --- | --- |
| 1. Credentials for FoaMES in the style the profile names: an API key, a bot, a technical user, or an OAuth client | The MES | You have the key, token, user name or client id and secret |
| 2. Create an **MES Connection** for the adapter (one per system), fill in the Base URL, the Site if the profile uses one, the authentication, any extra headers | FoaMES | **Test Connection** says "Connected to ..." (set a **Test Path** to a small read first) |
| 3. Add **Entity Mappings** for the reference types you need, from the vendor's API reference or your installation's service documentation | FoaMES | An External Reference of each type resolves |
| 4. Tick **Enabled** | FoaMES | New references of that system resolve |
| 5. Make sure the scheduler is enabled on the site | FoaMES | `bench --site <site> scheduler status` says enabled; queued postings move to Posted |

Writes are sent by the scheduler, so nothing leaves FoaMES until step 5 is in place, and **Pause
Outbox** on the connection holds them at any time.

## Entity mappings

A mapping row says how one reference type is found:

| Field | Meaning | Example (a part, Query lookup) | Example (an order, with a site parameter) |
| --- | --- | --- | --- |
| Path | Relative to the Base URL; may carry `{site}`, and for a Path lookup `{<key field>}` | `v1/parts` | `v1/orders` |
| Lookup | **Path** `GET <path>/<id>`; **Query** `GET <path>?<key>=<value>`; **OData** `$filter=<key> eq '<value>'`; **JSON Filter** `?filter={"<key>":"<value>"}` | Query | Query |
| Key Fields | Comma-separated, in External ID order; values joined by `\|` | `number` | `order` |
| Label Field | Dotted path to the text shown | `name` | `material.description` |
| Extra Query | Fixed parameters, `name=value&name=value`; values may carry `{site}` | | `plant={site}` |

A collection answer is unwrapped whatever its envelope (a plain list, OData `value` or `d.results`,
`_embedded`, `content`, `items`, `results`, `data`, `records`), and a filtered GET that answers with
the one record is taken as is. The first record is used, so the key should identify one record.

## The outbox

Every write is an **MES Outbox** record, sent by the scheduler. Code queues one with:

```python
from foames.foames_adapters.doctype.mes_outbox.mes_outbox import enqueue

enqueue(
	"<connection key>",
	"REST Request",
	{
		"method": "POST",
		"path": "<records path>",
		"body": {"order": "1000123", "good": 120, "scrap": 3},
		"reference_field": "<a field the system keeps and can search>",
		"lookup_path": "<records path>",
		"lookup_query": "<that field's query parameter>",
	},
	idempotency_key="<the business event, for example machine and window end>",
	sequence_group="<optional group sent in order>",
)
```

Every profile has the **REST Request** operation: the payload names the method (POST, PUT, PATCH or
DELETE), the path and the body. How the posting is kept from being performed twice depends on what
the system offers, and the payload says which:

| Kind | When | What happens after an unclear answer (timeout, dropped connection, 5xx) |
| --- | --- | --- |
| **Upsert** | A PUT, or `"idempotent": true`: the system keys the record on something in the body, so sending again overwrites | The posting goes to **Retry** and is sent again |
| **Client Reference** | `reference_field`, `lookup_path` and optionally `lookup_query` are given: the body carries a field the system keeps and can be searched by | FoaMES writes a 23-character marker into that field; the next attempt searches for it first and records the existing record instead of posting again |
| **Manual** | Neither | The posting stops in **Unknown** with **Needs Check** set and no next attempt. A person looks in the system, then **Mark Posted** (with the record's id), **Requeue** (sends it again) or **Cancel Posting** |

The rest follows the outbox rules every adapter keeps (see `foames/foames_adapters/AGENTS.md`). Queuing the same idempotency key twice returns the first record.
Throttling, server errors on reads, network failures and a rejected login are retried with exponential
backoff (1, 2, 4 ... minutes, up to 6 hours) for 12 attempts. A validation error or business rejection
marks the posting **Failed** with the system's message; fix the cause, then **Requeue**, or **Cancel
Posting**. Postings of one connection that share a sequence group are sent strictly in order, and a
failed or checked-pending one holds the rest of its group. **Pause Outbox** on the connection stops
sending without stopping queuing. The **ERP Outbox Health** report shows each connection as its own
adapter.

A vendor folder can add named operations to its profile when the vendor publishes a write API with a
stable path and a client reference: an `Operation` in `profile.py` with its method, path, required
fields, idempotency kind, reference field and lookup, plus a test in `mes/test_outbox_rules.py`
against the scripted fake. Keep the invariant: a posting is checked for before it is resent after an
unclear answer, or it is not resent at all.

## Day-to-day operation

- Watch the **ERP Outbox Health** report; each MES Connection is a row group of its own, and the
  **MES Outbox** list filtered on **Needs Check** shows what waits for a person.
- A Failed posting with a system message is fixed in the system or by correcting the payload, then
  requeued. A posting that needs a check is looked up in the system first.
- **Pause Outbox** on a connection before planned maintenance on that system.
- Reference lookups that fail because a system is unreachable, or because its credentials were
  rejected, leave the External Reference Unverified rather than blocking a save.
- Rotate a key, token or secret in the system and on the connection together; a 401 or 403 is treated
  as temporary on both paths.
- Each vendor licenses API use in its own way (named integrations, call quotas, Digital Access style
  document counting); check the contract before turning on writes.
