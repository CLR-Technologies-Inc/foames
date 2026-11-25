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

frappe.ui.form.on("Commissioning Test", {
	setup(frm) {
		frm.set_query("template", () => ({
			filters: { test_type: frm.doc.test_type, disabled: 0 },
		}));
	},
	refresh(frm) {
		if (frm.doc.package) {
			frm.add_custom_button(__("Package"), () =>
				frappe.set_route("Form", "Commissioning Package", frm.doc.package)
			);
		}
	},
	template(frm) {
		if (!frm.doc.template || (frm.doc.steps || []).length) return;
		frappe.db.get_doc("Commissioning Checklist Template", frm.doc.template).then((t) => {
			if (t.witness_required) frm.set_value("witness_required", 1);
			for (const item of t.items) {
				const row = frm.add_child("steps", {
					section: item.section,
					check_text: item.check_text,
					kind: item.kind,
					acceptance_criteria: item.acceptance_criteria,
					low_limit: item.low_limit,
					high_limit: item.high_limit,
					unit: item.unit,
					punch_category: item.punch_category || "B",
				});
				row.result = "Pending";
			}
			frm.refresh_field("steps");
		});
	},
});
