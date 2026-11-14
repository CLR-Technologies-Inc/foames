// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Punch Item", {
	refresh(frm) {
		if (frm.doc.source_doctype && frm.doc.source_name) {
			frm.add_custom_button(__("Raised From"), () =>
				frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name)
			);
		}
	},
	category(frm) {
		if (frm.doc.category === "A" && frm.doc.deferred) frm.set_value("deferred", 0);
	},
});
