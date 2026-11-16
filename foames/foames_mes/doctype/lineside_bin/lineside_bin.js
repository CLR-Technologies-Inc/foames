// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Lineside Bin", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Check now"), () =>
			frappe
				.call("foames.foames_mes.api.check_lineside_bin", { bin: frm.doc.name })
				.then(() => frm.reload_doc())
		);
	},
});
