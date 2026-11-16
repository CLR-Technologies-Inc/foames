// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.query_reports["Material Queue Status"] = {
	filters: [
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "queue", label: __("Queue"), fieldtype: "Link", options: "Material Queue" },
		{
			fieldname: "attention_only",
			label: __("Needs Attention Only"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "readiness" && data) {
			const colour = {
				Ready: "green",
				"Q-time Warning": "orange",
				"Q-time Exceeded": "red",
				Expired: "red",
				Conditioning: "blue",
				"On Hold": "grey",
				"In Process": "purple",
			}[data.readiness];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
