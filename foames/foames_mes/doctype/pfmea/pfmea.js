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

frappe.ui.form.on("PFMEA", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Observe Floor Now"), () =>
				frappe
					.call("foames.foames_mes.doctype.pfmea.pfmea.observe_now", {
						name: frm.doc.name,
					})
					.then((r) => {
						const m = r.message || {};
						frappe.show_alert({
							message: __(
								"{0} rows observed: {1} above their occurrence rating, {2} SPC signals",
								[m.rows, m.above_rating, m.spc_signals]
							),
							indicator: m.above_rating || m.spc_signals ? "orange" : "green",
						});
						frm.reload_doc();
					})
			);
		}
		frm.add_custom_button(
			__("Control Plan"),
			() => frappe.set_route("query-report", "PFMEA Control Plan", { pfmea: frm.doc.name }),
			__("View")
		);
		frm.add_custom_button(
			__("Risk Register"),
			() => frappe.set_route("query-report", "PFMEA Risk Register", { pfmea: frm.doc.name }),
			__("View")
		);
	},
});
