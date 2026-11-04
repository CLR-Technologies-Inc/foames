// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("MES Connection", {
	refresh(frm) {
		if (frm.doc.base_url && !frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), () => {
				frm.call("test_connection").then((r) => {
					frappe.show_alert({ message: r.message, indicator: "green" });
				});
			});
		}
		if (frm.doc.documentation_url) {
			frm.add_custom_button(__("API Documentation"), () => {
				window.open(frm.doc.documentation_url, "_blank");
			});
		}
	},
});
