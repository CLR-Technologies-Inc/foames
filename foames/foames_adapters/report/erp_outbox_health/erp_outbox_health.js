// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["ERP Outbox Health"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Created From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -6),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Created To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "adapter",
			label: __("Adapter"),
			fieldtype: "Select",
			options: ["", "ERPNext", "S/4HANA"],
		},
		{ fieldname: "operation", label: __("Operation"), fieldtype: "Data" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { Failed: "red", Retry: "orange", Unknown: "orange", Posted: "green" }[data.status];
			if (colour) value = `<span class="indicator-pill ${colour}">${data.status}</span>`;
		}
		return value;
	},
};
