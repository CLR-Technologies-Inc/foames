// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

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
