// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["Suggestion Status"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Raised From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -89),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Raised To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Category", "Severity", "Agent"],
			default: "Category",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: ["", "Yield", "Downtime", "Quality", "Release", "Machine Data", "ERP", "Other"],
		},
		{
			fieldname: "severity",
			label: __("Severity"),
			fieldtype: "Select",
			options: ["", "Info", "Warning", "Critical"],
		},
		{ fieldname: "agent", label: __("Agent"), fieldtype: "Data" },
	],
};
