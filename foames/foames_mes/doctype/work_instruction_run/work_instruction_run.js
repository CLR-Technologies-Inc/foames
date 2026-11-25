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

frappe.ui.form.on("Work Instruction Run", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (["In Progress", "On Hold"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Open on the Floor View"), () => {
				frappe.route_options = { work_instruction_run: frm.doc.name };
				frappe.set_route("floor-view");
			}).addClass("btn-primary");
		}
		if (frm.doc.status === "On Hold") {
			frm.set_intro(frappe.utils.escape_html(frm.doc.hold_reason || __("On hold")), "red");
		}
	},
});
