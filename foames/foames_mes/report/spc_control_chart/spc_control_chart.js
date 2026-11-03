// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["SPC Control Chart"] = {
	filters: [
		{
			fieldname: "machine",
			label: __("Machine"),
			fieldtype: "Link",
			options: "Machine",
			reqd: 1,
		},
		{ fieldname: "measurement", label: __("Measurement"), fieldtype: "Data", reqd: 1 },
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -6),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "chart",
			label: __("Chart"),
			fieldtype: "Select",
			options: ["I-MR", "X-bar R"],
			default: "I-MR",
		},
		{
			fieldname: "subgroup_size",
			label: __("Subgroup Size"),
			fieldtype: "Int",
			default: 5,
			depends_on: "eval:doc.chart=='X-bar R'",
		},
		{
			fieldname: "baseline_points",
			label: __("Baseline Readings"),
			fieldtype: "Int",
			description: __("Limits from the first N readings; 0 uses every reading"),
		},
		{
			fieldname: "rules",
			label: __("Run Rules"),
			fieldtype: "Select",
			options: ["Nelson", "Western Electric"],
			default: "Nelson",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const flagged =
			(column.fieldname === "value" && data && data.signals) ||
			(column.fieldname === "spread" && data && data.spread_signals);
		if (flagged) {
			value = `<span style="color:var(--red-600, red);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
