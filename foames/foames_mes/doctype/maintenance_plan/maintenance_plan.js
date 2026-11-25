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

frappe.ui.form.on("Maintenance Plan", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.open_work_order) {
			frm.add_custom_button(__("Open Work Order"), () =>
				frappe.set_route("Form", "Maintenance Work Order", frm.doc.open_work_order)
			);
		} else if (frappe.model.can_create("Maintenance Work Order")) {
			frm.add_custom_button(__("Create Work Order"), () =>
				frappe
					.call(
						"foames.foames_mes.doctype.maintenance_plan.maintenance_plan.make_work_order",
						{
							plan: frm.doc.name,
						}
					)
					.then((r) => frappe.set_route("Form", "Maintenance Work Order", r.message))
			);
		}
		frm.add_custom_button(__("Due List"), () =>
			frappe.set_route("query-report", "Maintenance Due List", { machine: frm.doc.machine })
		);
	},
});
