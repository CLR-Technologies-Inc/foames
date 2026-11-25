// Copyright 2026 CLR Technologies Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
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
