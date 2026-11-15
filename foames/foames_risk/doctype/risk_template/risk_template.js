// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Risk Template", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.disabled || !frappe.model.can_create("Enterprise Risk")) return;
		frm.add_custom_button(__("Create Risk"), () =>
			frappe
				.call(
					"foames.foames_risk.doctype.enterprise_risk.enterprise_risk.create_from_template",
					{ template: frm.doc.name }
				)
				.then((r) => frappe.set_route("Form", "Enterprise Risk", r.message))
		);
	},
});
