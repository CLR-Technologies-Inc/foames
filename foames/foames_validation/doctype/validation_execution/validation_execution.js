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

frappe.ui.form.on("Validation Execution", {
	setup(frm) {
		frm.set_query("protocol", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			const machine_rows = (frm.doc.results || []).filter(
				(r) => r.source === "Machine Data"
			);
			if (machine_rows.length) {
				frm.add_custom_button(__("Evaluate Machine Data"), () =>
					frappe
						.call(
							"foames.foames_validation.doctype.validation_execution.validation_execution.evaluate",
							{ name: frm.doc.name }
						)
						.then(() => frm.reload_doc())
				);
			}
		}
		if (frm.doc.open_items && frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(
				__("Open items: {0}", [
					frappe.utils.escape_html(frm.doc.open_items).replace(/\n/g, "; "),
				])
			);
		}
	},
});
