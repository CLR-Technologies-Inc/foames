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

frappe.ui.form.on("Maintenance Work Order", {
	refresh(frm) {
		if (frm.is_new() || !frm.perm[0].write) return;
		if (frm.doc.status === "Open") {
			frm.add_custom_button(__("Start"), () => {
				frm.set_value("status", "In Progress");
				frm.save();
			});
		}
		if (["Open", "In Progress"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Complete"), () => {
				frm.set_value("status", "Completed");
				frm.save();
			}).addClass("btn-primary");
		}
	},
});
