// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

const HEAT_COLOURS = {
	"Very Low": "var(--green-100)",
	Low: "var(--green-300)",
	Moderate: "var(--yellow-300)",
	High: "var(--orange-400)",
	"Very High": "var(--red-400)",
};

frappe.query_reports["Risk Heat Map"] = {
	filters: [
		{
			fieldname: "basis",
			label: __("Basis"),
			fieldtype: "Select",
			options: "Residual\nInherent",
			default: "Residual",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Link",
			options: "Risk Category",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const match = /^l([1-5])$/.exec(column.fieldname);
		if (match && data) {
			const colour = HEAT_COLOURS[data[`r${match[1]}`]];
			return `<div style="background: ${colour}; text-align: center; font-weight: 600">${value}</div>`;
		}
		return value;
	},
};
