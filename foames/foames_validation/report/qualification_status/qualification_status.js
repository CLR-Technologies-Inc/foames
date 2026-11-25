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

frappe.query_reports["Qualification Status"] = {
	filters: [
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "process", label: __("Process"), fieldtype: "Data" },
		{
			fieldname: "protocol_type",
			label: __("Type"),
			fieldtype: "Select",
			options: ["", "IQ", "OQ", "PQ", "PPQ", "CPV"],
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Qualified", "Due Soon", "Expired", "Runs Pending", "Not Qualified"],
		},
		{
			fieldname: "due_soon_days",
			label: __("Due Soon Within (Days)"),
			fieldtype: "Int",
			default: 30,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = {
				Qualified: "green",
				"Due Soon": "orange",
				Expired: "red",
				"Not Qualified": "red",
				"Runs Pending": "blue",
			}[data.status];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
