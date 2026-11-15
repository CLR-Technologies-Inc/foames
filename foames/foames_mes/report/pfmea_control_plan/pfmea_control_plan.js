// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.query_reports["PFMEA Control Plan"] = {
	filters: [
		{ fieldname: "pfmea", label: __("PFMEA"), fieldtype: "Link", options: "PFMEA" },
		{ fieldname: "process_line", label: __("Process / Line"), fieldtype: "Data" },
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{
			fieldname: "special_only",
			label: __("Special Characteristics Only"),
			fieldtype: "Check",
		},
	],
};
