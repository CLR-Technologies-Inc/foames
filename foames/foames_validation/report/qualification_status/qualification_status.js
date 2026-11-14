// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["Qualification Status"] = {
	filters: [
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "process", label: __("Process"), fieldtype: "Data" },
		{
			fieldname: "protocol_type",
			label: __("Type"),
			fieldtype: "Select",
			options: ["", "IQ", "OQ", "PQ", "PPQ", "CPV"],
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Qualified", "Due Soon", "Expired", "Runs Pending", "Not Qualified"],
		},
		{ fieldname: "due_soon_days", label: __("Due Soon Within (Days)"), fieldtype: "Int", default: 30 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = {
				Qualified: "green",
				"Due Soon": "orange",
				Expired: "red",
				"Not Qualified": "red",
				"Runs Pending": "blue",
			}[data.status];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
