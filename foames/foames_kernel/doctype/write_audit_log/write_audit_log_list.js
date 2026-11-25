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

frappe.listview_settings["Write Audit Log"] = {
	onload(listview) {
		if (!frappe.user.has_role(["System Manager", "FoaMES Quality"])) return;
		listview.page.add_inner_button(__("Verify Chain"), () =>
			frappe.call("foames.foames_kernel.write_gate.verify_audit_trail").then((r) => {
				const v = r.message || {};
				frappe.msgprint(
					v.intact
						? __("All {0} entries are intact.", [v.entries])
						: __("{0} of {1} entries do not match: {2}", [
								v.broken.length,
								v.entries,
								v.broken.join(", "),
						  ])
				);
			})
		);
	},
};
