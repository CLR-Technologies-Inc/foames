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

frappe.query_reports["Material Queue Status"] = {
	filters: [
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{ fieldname: "queue", label: __("Queue"), fieldtype: "Link", options: "Material Queue" },
		{
			fieldname: "attention_only",
			label: __("Needs Attention Only"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "readiness" && data) {
			const colour = {
				Ready: "green",
				"Q-time Warning": "orange",
				"Q-time Exceeded": "red",
				Expired: "red",
				Conditioning: "blue",
				"On Hold": "grey",
				"In Process": "purple",
			}[data.readiness];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
