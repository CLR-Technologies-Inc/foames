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

"""Introduce read-only mode on a site that already runs FoaMES, without stopping what already works.

A new site starts read-only (see install.py). An existing site is upgraded so that nothing changes on
the day: site-wide read-only mode stays off, and every connector that has already written (it has
rows in a gated outbox, or the MCP server was available) gets a read-write Connector Write Policy.
Connectors configured after the upgrade start read-only. Each policy created here is logged in the
Write Audit Log, so the state after the upgrade is on record.
"""

import frappe

from foames.foames_kernel import write_gate
from foames.install import set_read_only_defaults

APPROVAL = "Writable before read-only mode was installed"


def execute():
	set_read_only_defaults(site_read_only=False)
	connectors = {write_gate.MCP_CONNECTOR: ("FoaMES MCP server", "Agent")}
	for doctype, spec in write_gate.gated_outboxes().items():
		if not frappe.db.table_exists(doctype) or not frappe.db.count(doctype):
			continue
		if spec.startswith("field:"):
			field = spec.split(":", 1)[1]
			for key in frappe.get_all(doctype, pluck=field, distinct=True):
				if key:
					connectors.setdefault(key, (key, ""))
		else:
			connectors.setdefault(spec, (spec, ""))
	for key, (label, kind) in connectors.items():
		if frappe.db.exists("Connector Write Policy", key):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Connector Write Policy",
				"connector": key,
				"connector_label": label,
				"connector_kind": kind,
				"read_only": 0,
				"when_read_only": "Site default",
				"approval_reference": APPROVAL,
				"notes": "Created by the upgrade that introduced read-only mode, so this connector kept writing. "
				"Check Read-only to require sign-off for its writes.",
			}
		)
		doc.insert(ignore_permissions=True)
