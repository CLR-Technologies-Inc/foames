// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Write Audit Log", {
	refresh(frm) {
		frm.disable_save();
	},
});
