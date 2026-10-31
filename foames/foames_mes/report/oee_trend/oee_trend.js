// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["OEE Trend"] = {
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
			options: ["Machine", "Line", "Day"],
			default: "Machine",
		},
		{
			fieldname: "metric",
			label: __("Chart Metric"),
			fieldtype: "Select",
			options: ["OEE", "Availability", "Performance", "Quality"],
			default: "OEE",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "oee" && data && data.oee !== undefined) {
			const colour = data.oee >= 85 ? "green" : data.oee >= 60 ? "orange" : "red";
			value = `<span style="color:var(--${colour}-600, ${colour})">${value}</span>`;
		}
		return value;
	},
};
