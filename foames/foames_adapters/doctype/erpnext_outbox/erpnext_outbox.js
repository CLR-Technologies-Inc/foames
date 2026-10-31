// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("ERPNext Outbox", {
	refresh(frm) {
		if (frm.doc.status === "Failed") {
			frm.add_custom_button(__("Requeue"), () => {
				frm.call("requeue").then(() => frm.reload_doc());
			});
		}
		if (!["Posted", "Sending", "Cancelled"].includes(frm.doc.status) && !frm.is_new()) {
			frm.add_custom_button(__("Cancel Posting"), () => {
				const message = __(
					"Drop this posting? Later ones in its group are then performed."
				);
				frappe.confirm(message, () => {
					frm.call("cancel_posting").then(() => frm.reload_doc());
				});
			});
		}
		if (frm.doc.erp_doctype && frm.doc.erp_document) {
			frm.add_custom_button(__("Open {0}", [frm.doc.erp_doctype]), () => {
				frappe.set_route("Form", frm.doc.erp_doctype, frm.doc.erp_document);
			});
		}
	},
});
