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

frappe.query_reports["SPC Control Chart"] = {
	filters: [
		{
			fieldname: "machine",
			label: __("Machine"),
			fieldtype: "Link",
			options: "Machine",
			reqd: 1,
		},
		{ fieldname: "measurement", label: __("Measurement"), fieldtype: "Data", reqd: 1 },
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -6),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "chart",
			label: __("Chart"),
			fieldtype: "Select",
			options: ["I-MR", "X-bar R"],
			default: "I-MR",
		},
		{
			fieldname: "subgroup_size",
			label: __("Subgroup Size"),
			fieldtype: "Int",
			default: 5,
			depends_on: "eval:doc.chart=='X-bar R'",
		},
		{
			fieldname: "baseline_points",
			label: __("Baseline Readings"),
			fieldtype: "Int",
			description: __("Limits from the first N readings; 0 uses every reading"),
		},
		{
			fieldname: "rules",
			label: __("Run Rules"),
			fieldtype: "Select",
			options: ["Nelson", "Western Electric"],
			default: "Nelson",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const flagged =
			(column.fieldname === "value" && data && data.signals) ||
			(column.fieldname === "spread" && data && data.spread_signals);
		if (flagged) {
			value = `<span style="color:var(--red-600, red);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
