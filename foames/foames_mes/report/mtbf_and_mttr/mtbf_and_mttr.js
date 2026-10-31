// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["MTBF and MTTR"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -29),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "line", label: __("Line"), fieldtype: "Data" },
		{
			fieldname: "breakdowns_only",
			label: __("Breakdown Reasons Only"),
			fieldtype: "Check",
			default: 0,
			description: __("Count only stoppages whose reason has the category Breakdown"),
		},
	],
};
