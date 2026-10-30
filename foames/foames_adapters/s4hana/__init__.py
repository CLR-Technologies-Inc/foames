# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""SAP S/4HANA adapter.

S/4HANA runs on its own server, so unlike the ERPNext adapter this one is remote:

- References are resolved over SAP's released OData APIs (`odata.py`, `entities.py`).
- Postings to S/4HANA (confirmations, goods movements) go through an outbox with idempotency keys,
  retries and per-order sequencing (`outbox.py`), because S/4HANA can reject a posting long after
  the operator has moved on.
- Order, material and batch downloads arrive as IDocs posted over HTTP (`idoc.py`).

Nothing here uses RFC or the SAP NetWeaver RFC SDK, and no SAP code or API metadata ships with it.
The modules named above are plain Python with no Frappe imports; `adapter.py` and `api.py` hold the
Frappe side.
"""
