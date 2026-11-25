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

frappe.query_reports["Utility Consumption"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -29),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: "Day\nWeek\nMonth",
			default: "Day",
		},
		{
			fieldname: "utility",
			label: __("Utility"),
			fieldtype: "Select",
			options:
				"\nElectricity\nNatural Gas\nWater\nWastewater\nChilled Water\nHeating Hot Water\nSteam\nCompressed Air",
		},
		{ fieldname: "zone", label: __("Zone"), fieldtype: "Link", options: "Facility Zone" },
		{
			fieldname: "facility_asset",
			label: __("Facility Asset"),
			fieldtype: "Link",
			options: "Facility Asset",
		},
	],
};
