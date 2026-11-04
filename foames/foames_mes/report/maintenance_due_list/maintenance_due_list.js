// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["Maintenance Due List"] = {
	filters: [
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "line", label: __("Line"), fieldtype: "Data" },
		{
			fieldname: "trigger",
			label: __("Trigger"),
			fieldtype: "Select",
			options: ["", "Calendar", "Run Hours", "Count"],
		},
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Due Soon or later", "Due or Overdue", "All plans"],
			default: "Due Soon or later",
		},
		{
			fieldname: "horizon_days",
			label: __("Also Due Within (Days)"),
			fieldtype: "Int",
			default: 0,
			description: __("Also list OK plans whose due date falls within this many days"),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { Overdue: "red", Due: "orange", "Due Soon": "yellow", OK: "green" }[
				data.status
			];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
