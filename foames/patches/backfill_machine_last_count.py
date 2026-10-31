# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder.functions import Max


def execute():
	"""Fill Machine.last_count_at from the Count events recorded before the field existed."""
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.machine, Max(event.timestamp).as_("last"))
		.where(event.event_type == "Count")
		.groupby(event.machine)
		.run(as_dict=True)
	)
	for row in rows:
		frappe.db.set_value("Machine", row.machine, "last_count_at", row.last, update_modified=False)
