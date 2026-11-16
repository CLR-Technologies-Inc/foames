// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("External Reference", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Resolve"), () => {
				frm.call("resolve").then(() => frm.reload_doc());
			});
		}
	},
});
