// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Commissioning Test", {
	setup(frm) {
		frm.set_query("template", () => ({
			filters: { test_type: frm.doc.test_type, disabled: 0 },
		}));
	},
	refresh(frm) {
		if (frm.doc.package) {
			frm.add_custom_button(__("Package"), () =>
				frappe.set_route("Form", "Commissioning Package", frm.doc.package)
			);
		}
	},
	template(frm) {
		if (!frm.doc.template || (frm.doc.steps || []).length) return;
		frappe.db.get_doc("Commissioning Checklist Template", frm.doc.template).then((t) => {
			if (t.witness_required) frm.set_value("witness_required", 1);
			for (const item of t.items) {
				const row = frm.add_child("steps", {
					section: item.section,
					check_text: item.check_text,
					kind: item.kind,
					acceptance_criteria: item.acceptance_criteria,
					low_limit: item.low_limit,
					high_limit: item.high_limit,
					unit: item.unit,
					punch_category: item.punch_category || "B",
				});
				row.result = "Pending";
			}
			frm.refresh_field("steps");
		});
	},
});
