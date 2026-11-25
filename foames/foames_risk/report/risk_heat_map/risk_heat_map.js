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

const HEAT_COLOURS = {
	"Very Low": "var(--green-100)",
	Low: "var(--green-300)",
	Moderate: "var(--yellow-300)",
	High: "var(--orange-400)",
	"Very High": "var(--red-400)",
};

frappe.query_reports["Risk Heat Map"] = {
	filters: [
		{
			fieldname: "basis",
			label: __("Basis"),
			fieldtype: "Select",
			options: "Residual\nInherent",
			default: "Residual",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Link",
			options: "Risk Category",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const match = /^l([1-5])$/.exec(column.fieldname);
		if (match && data) {
			const colour = HEAT_COLOURS[data[`r${match[1]}`]];
			return `<div style="background: ${colour}; text-align: center; font-weight: 600">${value}</div>`;
		}
		return value;
	},
};
