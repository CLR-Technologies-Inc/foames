// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Loop Check", {
	refresh(frm) {
		if (frm.doc.punch_item) {
			frm.add_custom_button(__("Punch Item"), () =>
				frappe.set_route("Form", "Punch Item", frm.doc.punch_item)
			);
		}
	},
});
