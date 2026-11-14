// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Validation Execution", {
	setup(frm) {
		frm.set_query("protocol", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			const machine_rows = (frm.doc.results || []).filter(
				(r) => r.source === "Machine Data"
			);
			if (machine_rows.length) {
				frm.add_custom_button(__("Evaluate Machine Data"), () =>
					frappe
						.call(
							"foames.foames_validation.doctype.validation_execution.validation_execution.evaluate",
							{ name: frm.doc.name }
						)
						.then(() => frm.reload_doc())
				);
			}
		}
		if (frm.doc.open_items && frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(
				__("Open items: {0}", [
					frappe.utils.escape_html(frm.doc.open_items).replace(/\n/g, "; "),
				])
			);
		}
	},
});
