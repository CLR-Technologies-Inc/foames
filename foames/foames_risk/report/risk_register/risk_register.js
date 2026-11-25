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

frappe.query_reports["Risk Register"] = {
	filters: [
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Link",
			options: "Risk Category",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nIdentified\nAssessed\nTreating\nMonitoring\nClosed",
		},
		{
			fieldname: "residual_rating",
			label: __("Residual Rating"),
			fieldtype: "Select",
			options: "\nVery Low\nLow\nModerate\nHigh\nVery High",
		},
		{
			fieldname: "objective",
			label: __("Objective"),
			fieldtype: "Select",
			options: "\nStrategic\nOperations\nReporting\nCompliance",
		},
		{ fieldname: "risk_owner", label: __("Risk Owner"), fieldtype: "Link", options: "User" },
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "above_tolerance", label: __("Above Tolerance Only"), fieldtype: "Check" },
		{ fieldname: "include_closed", label: __("Include Closed"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "residual_rating" && data && !data.within_tolerance) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
