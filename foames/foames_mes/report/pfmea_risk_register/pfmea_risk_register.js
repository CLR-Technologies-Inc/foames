// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["PFMEA Risk Register"] = {
	filters: [
		{ fieldname: "pfmea", label: __("PFMEA"), fieldtype: "Link", options: "PFMEA" },
		{ fieldname: "process", label: __("Process / Line"), fieldtype: "Data" },
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{
			fieldname: "action_priority",
			label: __("Action Priority"),
			fieldtype: "Select",
			options: ["", "H", "M", "L"],
		},
		{ fieldname: "open_actions_only", label: __("Open Actions Only"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (
			data &&
			(column.fieldname === "action_priority" || column.fieldname === "new_action_priority")
		) {
			const colour = { H: "red", M: "orange", L: "green" }[data[column.fieldname]];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (
			data &&
			column.fieldname === "observed_occurrence" &&
			data.observed_occurrence > (data.occurrence || 10)
		) {
			value = `<span class="indicator-pill red">${value}</span>`;
		}
		return value;
	},
};
