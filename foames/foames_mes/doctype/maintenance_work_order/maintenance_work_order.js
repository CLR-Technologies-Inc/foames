// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Maintenance Work Order", {
	refresh(frm) {
		if (frm.is_new() || !frm.perm[0].write) return;
		if (frm.doc.status === "Open") {
			frm.add_custom_button(__("Start"), () => {
				frm.set_value("status", "In Progress");
				frm.save();
			});
		}
		if (["Open", "In Progress"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Complete"), () => {
				frm.set_value("status", "Completed");
				frm.save();
			}).addClass("btn-primary");
		}
	},
});
