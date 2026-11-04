# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The shared framework behind the adapters for other MES and MOM systems.

FoaMES is often not the only manufacturing system in a plant: an enterprise MES or MOM suite, or a
frontline platform, holds the orders, materials and equipment, and FoaMES reads the machines. Each
of them is reached through its own HTTPS API, and they differ in how a caller logs in, how a record
is addressed and how an answer is wrapped, but not in what FoaMES needs of them: resolve an External
Reference, and queue a write that is never performed twice.

So each system has a vendor folder next to this one that holds a **profile**: the adapter's key
and label, where its public API documentation lives, how it authenticates, the base URL pattern,
the entity lookups that are documented well enough to ship as defaults, and the outbox operations
it offers. This package holds what they share:

- `rest.py`: a JSON REST client with the authentication styles these systems use (Basic, a static
  bearer token, an API key header, OAuth 2.0 client credentials), transport injected.
- `entities.py`: how a kernel reference type maps to a resource: a path, a lookup style (by path,
  query parameter, OData filter or JSON filter), key fields and a label field.
- `profile.py`: the profile dataclass and the operation definitions.
- `outbox.py`: the outbox rules. An operation says how it is idempotent: an upsert, a client
  reference the system keeps and can be searched by, or neither, in which case an unclear answer
  stops the posting for a person to check instead of resending it blind.
- `adapter.py`: the Frappe side, reading one **MES Connection** per adapter key.

Those five modules and `fake.py` import nothing from Frappe except `adapter.py`. The site records
are **MES Connection** (one per system, with its secrets in Password fields), **MES Entity Mapping**
and **MES Outbox**.
"""
