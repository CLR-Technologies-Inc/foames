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

frappe.query_reports["PFMEA Risk Register"] = {
	filters: [
		{ fieldname: "pfmea", label: __("PFMEA"), fieldtype: "Link", options: "PFMEA" },
		{ fieldname: "process_line", label: __("Process / Line"), fieldtype: "Data" },
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{
			fieldname: "action_priority",
			label: __("Action Priority"),
			fieldtype: "Select",
			options: ["", "H", "M", "L"],
		},
		{ fieldname: "open_actions_only", label: __("Open Actions Only"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (
			data &&
			(column.fieldname === "action_priority" || column.fieldname === "new_action_priority")
		) {
			const colour = { H: "red", M: "orange", L: "green" }[data[column.fieldname]];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (
			data &&
			column.fieldname === "observed_occurrence" &&
			data.observed_occurrence > (data.occurrence || 10)
		) {
			value = `<span class="indicator-pill red">${value}</span>`;
		}
		return value;
	},
};
