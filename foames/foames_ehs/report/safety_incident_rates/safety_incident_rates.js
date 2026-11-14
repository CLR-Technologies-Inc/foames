// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["Safety Incident Rates"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "hours_worked",
			label: __("Hours Worked"),
			fieldtype: "Float",
			description: __(
				"Total hours worked by everyone covered in the period; the rates are per 200,000 hours",
			),
		},
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "location", label: __("Location"), fieldtype: "Data" },
	],
};
