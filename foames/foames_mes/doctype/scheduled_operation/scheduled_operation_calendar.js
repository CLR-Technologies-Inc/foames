// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

// Calendar and Gantt views of the scheduled operations: /app/scheduled-operation/view/gantt
frappe.views.calendar["Scheduled Operation"] = {
	field_map: {
		start: "start_time",
		end: "end_time",
		id: "name",
		title: "title",
		progress: "progress",
	},
	gantt: true,
	filters: [
		{
			fieldtype: "Link",
			fieldname: "production_schedule",
			options: "Production Schedule",
			label: __("Production Schedule"),
		},
		{
			fieldtype: "Link",
			fieldname: "machine",
			options: "Machine",
			label: __("Machine"),
		},
	],
	get_events_method: "frappe.desk.calendar.get_events",
};
