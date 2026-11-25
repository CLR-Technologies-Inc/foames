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

frappe.query_reports["Maintenance Due List"] = {
	filters: [
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "line", label: __("Line"), fieldtype: "Data" },
		{
			fieldname: "trigger",
			label: __("Trigger"),
			fieldtype: "Select",
			options: ["", "Calendar", "Run Hours", "Count"],
		},
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Due Soon or later", "Due or Overdue", "All plans"],
			default: "Due Soon or later",
		},
		{
			fieldname: "horizon_days",
			label: __("Also Due Within (Days)"),
			fieldtype: "Int",
			default: 0,
			description: __("Also list OK plans whose due date falls within this many days"),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colour = { Overdue: "red", Due: "orange", "Due Soon": "yellow", OK: "green" }[
				data.status
			];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
