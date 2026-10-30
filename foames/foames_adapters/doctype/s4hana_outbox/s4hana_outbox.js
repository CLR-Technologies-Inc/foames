// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("S4HANA Outbox", {
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
