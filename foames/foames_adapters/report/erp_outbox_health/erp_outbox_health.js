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

frappe.query_reports["ERP Outbox Health"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Created From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -6),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Created To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "adapter",
			label: __("Adapter"),
			fieldtype: "Data",
			description: __(
				"ERPNext, S/4HANA, Insights Hub, or an MES Connection such as SAP_DMC or PLEX"
			),
		},
		{ fieldname: "operation", label: __("Operation"), fieldtype: "Data" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const colours = { Failed: "red", Retry: "orange", Unknown: "orange", Posted: "green" };
			const colour = colours[data.status];
			if (colour) value = `<span class="indicator-pill ${colour}">${data.status}</span>`;
		}
		return value;
	},
};
