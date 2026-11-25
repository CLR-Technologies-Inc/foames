# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

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
