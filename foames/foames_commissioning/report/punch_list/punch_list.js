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

frappe.query_reports["Punch List"] = {
	filters: [
		{
			fieldname: "package",
			label: __("Package"),
			fieldtype: "Link",
			options: "Commissioning Package",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: ["", "A", "B", "C"],
		},
		{ fieldname: "assigned_to", label: __("Assigned To"), fieldtype: "Link", options: "User" },
		{ fieldname: "equipment_tag", label: __("Equipment Tag"), fieldtype: "Data" },
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Open items", "Closed items", "All items"],
			default: "Open items",
		},
		{ fieldname: "overdue_only", label: __("Overdue Only"), fieldtype: "Check", default: 0 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "category" && data) {
			const colour = { A: "red", B: "orange", C: "blue" }[data.category];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
