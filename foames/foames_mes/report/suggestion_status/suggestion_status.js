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

frappe.query_reports["Suggestion Status"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Raised From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -89),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Raised To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Category", "Severity", "Agent"],
			default: "Category",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: [
				"",
				"Yield",
				"Downtime",
				"Quality",
				"Release",
				"Machine Data",
				"Maintenance",
				"ERP",
				"Other",
			],
		},
		{
			fieldname: "severity",
			label: __("Severity"),
			fieldtype: "Select",
			options: ["", "Info", "Warning", "Critical"],
		},
		{ fieldname: "agent", label: __("Agent"), fieldtype: "Data" },
	],
};
