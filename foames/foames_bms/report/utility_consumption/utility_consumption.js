// Copyright (c) 2026 CLR Technologies Inc. and contributors
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
