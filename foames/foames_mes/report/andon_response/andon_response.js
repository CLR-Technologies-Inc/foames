// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["Andon Response"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Raised From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -29),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Raised To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "line", label: __("Line"), fieldtype: "Data" },
		{
			fieldname: "call_type",
			label: __("Call Type"),
			fieldtype: "Link",
			options: "Andon Call Type",
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Call Type", "Machine", "Line"],
			default: "Call Type",
		},
	],
};
