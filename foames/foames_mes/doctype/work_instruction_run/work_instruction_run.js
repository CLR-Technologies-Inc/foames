// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Work Instruction Run", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (["In Progress", "On Hold"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Open on the Floor View"), () => {
				frappe.route_options = { work_instruction_run: frm.doc.name };
				frappe.set_route("floor-view");
			}).addClass("btn-primary");
		}
		if (frm.doc.status === "On Hold") {
			frm.set_intro(frappe.utils.escape_html(frm.doc.hold_reason || __("On hold")), "red");
		}
	},
});
