# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Siemens Insights Hub adapter, for Opcenter Intelligence.

Insights Hub (formerly MindSphere) is Siemens' industrial IoT platform; Opcenter Intelligence is the
manufacturing-intelligence application that runs on it and reads production data from the
platform's asset model, time series and events. Like S/4HANA, Insights Hub runs on its own servers,
so this adapter is remote and works over HTTPS through the platform gateway:

- References are resolved over the platform's REST APIs (`rest.py`, `entities.py`): a Workstation or
  a Location is an Insights Hub asset; the Opcenter Intelligence resources a site uses (materials,
  orders, operations, batches) are mapped in Insights Hub Settings against the published API
  reference.
- Writes to Insights Hub (machine production as time series, state changes as events) go through an
  outbox with idempotency keys, retries and sequence groups (`outbox.py`), the same model as the
  S/4HANA outbox.
- Each machine's good and scrap counts and running time are rolled up into time series records on
  the machine's asset (`production.py`, `rollup.py`), which is what Opcenter Intelligence reads.

No Siemens code, SDK or API metadata ships with the adapter: it talks to the released REST APIs
only, with the Python standard library. `rest.py`, `entities.py`, `outbox.py`, `production.py` and
`fake.py` import nothing from Frappe; `adapter.py` and `rollup.py` hold the Frappe side.
"""

ADAPTER_KEY = "INSIGHTS_HUB"
