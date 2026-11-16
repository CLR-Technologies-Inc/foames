// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Insights Hub Settings", {
	refresh(frm) {
		if (frm.doc.gateway_url) {
			frm.add_custom_button(__("Test Connection"), () => {
				frm.call("test_connection").then((r) => {
					frappe.show_alert({ message: r.message, indicator: "green" });
				});
			});
		}
	},
});
