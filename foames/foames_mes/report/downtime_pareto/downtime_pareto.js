// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["Downtime Pareto"] = {
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
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Reason", "Category", "Machine"],
			default: "Reason",
		},
		{
			fieldname: "include_planned",
			label: __("Include Planned Downtime"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_open",
			label: __("Include Open Stoppages"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
