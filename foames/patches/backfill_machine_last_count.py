# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Fill Machine.last_count_at from the Count events recorded before the field existed."""
	for row in frappe.get_all(
		"Machine Event",
		{"event_type": "Count"},
		["machine", "max(timestamp) as last"],
		group_by="machine",
	):
		frappe.db.set_value("Machine", row.machine, "last_count_at", row.last, update_modified=False)
