// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["SOP Training Matrix"] = {
	filters: [
		{ fieldname: "sop_code", label: __("SOP Code"), fieldtype: "Data" },
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: [
				"",
				"Operations",
				"Quality",
				"Safety",
				"Maintenance",
				"Engineering",
				"Other",
			],
		},
		{ fieldname: "user", label: __("User"), fieldtype: "Link", options: "User" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Current", "Outdated", "Missing"],
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { Current: "green", Outdated: "orange", Missing: "red" }[data.status];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
