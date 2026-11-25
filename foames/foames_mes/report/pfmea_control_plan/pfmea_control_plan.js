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

frappe.query_reports["PFMEA Control Plan"] = {
	filters: [
		{ fieldname: "pfmea", label: __("PFMEA"), fieldtype: "Link", options: "PFMEA" },
		{ fieldname: "process_line", label: __("Process / Line"), fieldtype: "Data" },
		{ fieldname: "machine", label: __("Machine"), fieldtype: "Link", options: "Machine" },
		{
			fieldname: "special_only",
			label: __("Special Characteristics Only"),
			fieldtype: "Check",
		},
	],
};
