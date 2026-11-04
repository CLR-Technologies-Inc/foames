// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Maintenance Plan", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.open_work_order) {
			frm.add_custom_button(__("Open Work Order"), () =>
				frappe.set_route("Form", "Maintenance Work Order", frm.doc.open_work_order)
			);
		} else if (frappe.model.can_create("Maintenance Work Order")) {
			frm.add_custom_button(__("Create Work Order"), () =>
				frappe
					.call(
						"foames.foames_mes.doctype.maintenance_plan.maintenance_plan.make_work_order",
						{
							plan: frm.doc.name,
						}
					)
					.then((r) => frappe.set_route("Form", "Maintenance Work Order", r.message))
			);
		}
		frm.add_custom_button(__("Due List"), () =>
			frappe.set_route("query-report", "Maintenance Due List", { machine: frm.doc.machine })
		);
	},
});
