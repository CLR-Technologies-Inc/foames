// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.query_reports["Commissioning Status"] = {
	filters: [
		{ fieldname: "line", label: __("Line"), fieldtype: "Data" },
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Open packages", "All packages"],
			default: "Open packages",
		},
	],
};
