// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.query_reports["Process Throughput"] = {
	filters: [
		{
			fieldname: "event_log",
			label: __("Process Event Log"),
			fieldtype: "Link",
			options: "Process Event Log",
			get_query: () => ({ filters: { status: "Extracted" } }),
			description: __("Leave empty for the latest extracted log"),
		},
		{
			fieldname: "interval",
			label: __("Interval"),
			fieldtype: "Select",
			options: ["Daily", "Weekly"],
			default: "Daily",
		},
		{
			fieldname: "completing_activity",
			label: __("Only Cases With Activity"),
			fieldtype: "Data",
		},
	],
};
