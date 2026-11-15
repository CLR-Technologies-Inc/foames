// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.query_reports["Punch List"] = {
	filters: [
		{
			fieldname: "package",
			label: __("Package"),
			fieldtype: "Link",
			options: "Commissioning Package",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: ["", "A", "B", "C"],
		},
		{ fieldname: "assigned_to", label: __("Assigned To"), fieldtype: "Link", options: "User" },
		{ fieldname: "equipment_tag", label: __("Equipment Tag"), fieldtype: "Data" },
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Open items", "Closed items", "All items"],
			default: "Open items",
		},
		{ fieldname: "overdue_only", label: __("Overdue Only"), fieldtype: "Check", default: 0 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "category" && data) {
			const colour = { A: "red", B: "orange", C: "blue" }[data.category];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
