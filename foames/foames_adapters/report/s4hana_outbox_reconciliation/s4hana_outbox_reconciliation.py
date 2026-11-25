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

"""Postings that still need attention: failed, waiting to retry, unconfirmed, or held behind an
earlier posting of the same group."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	if not filters.include_posted:
		conditions["status"] = ("not in", ("Posted", "Cancelled"))
	if filters.sequence_group:
		conditions["sequence_group"] = filters.sequence_group

	rows = frappe.get_all(
		"S4HANA Outbox",
		filters=conditions,
		fields=[
			"name",
			"operation",
			"status",
			"sequence_group",
			"attempts",
			"next_attempt_at",
			"sap_document",
			"last_error",
			"reference_doctype",
			"reference_name",
			"creation",
		],
		order_by="creation asc",
	)

	# The first unposted row of each group holds every later row of that group.
	first_open = {}
	for row in rows:
		group = row.sequence_group
		if group and row.status not in ("Posted", "Cancelled"):
			if group in first_open:
				row.held_by = first_open[group]
			else:
				first_open[group] = row.name

	columns = [
		{
			"fieldname": "name",
			"label": _("Posting"),
			"fieldtype": "Link",
			"options": "S4HANA Outbox",
			"width": 140,
		},
		{"fieldname": "operation", "label": _("Operation"), "fieldtype": "Data", "width": 200},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "sequence_group", "label": _("Sequence Group"), "fieldtype": "Data", "width": 140},
		{
			"fieldname": "held_by",
			"label": _("Held By"),
			"fieldtype": "Link",
			"options": "S4HANA Outbox",
			"width": 140,
		},
		{"fieldname": "attempts", "label": _("Attempts"), "fieldtype": "Int", "width": 80},
		{"fieldname": "next_attempt_at", "label": _("Next Attempt"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "sap_document", "label": _("S/4HANA Document"), "fieldtype": "Data", "width": 160},
		{"fieldname": "last_error", "label": _("Last Error"), "fieldtype": "Data", "width": 300},
		{
			"fieldname": "reference_doctype",
			"label": _("Source Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 120,
		},
		{
			"fieldname": "reference_name",
			"label": _("Source"),
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 140,
		},
	]
	return columns, rows
