// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Validation Protocol", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("New Execution"), () =>
				frappe.new_doc("Validation Execution", { protocol: frm.doc.name })
			);
		}
	},
});
