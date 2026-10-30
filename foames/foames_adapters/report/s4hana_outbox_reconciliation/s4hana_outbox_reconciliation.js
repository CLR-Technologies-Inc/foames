// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["S4HANA Outbox Reconciliation"] = {
	filters: [
		{
			fieldname: "include_posted",
			label: __("Include Posted"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "sequence_group",
			label: __("Sequence Group"),
			fieldtype: "Data",
		},
	],
};
