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

frappe.ui.form.on("Insights Hub Outbox", {
	refresh(frm) {
		if (frm.doc.status === "Failed") {
			frm.add_custom_button(__("Requeue"), () => {
				frm.call("requeue").then(() => frm.reload_doc());
			});
		}
		if (!["Posted", "Sending", "Cancelled"].includes(frm.doc.status) && !frm.is_new()) {
			frm.add_custom_button(__("Cancel Posting"), () => {
				const message = __("Drop this posting? Later ones in its group are then sent.");
				frappe.confirm(message, () => {
					frm.call("cancel_posting").then(() => frm.reload_doc());
				});
			});
		}
	},
});
