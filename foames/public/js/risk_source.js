// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

// A "Create Enterprise Risk" button on the detailed assessments a risk can summarise. The new risk
// links back to the record as its Source; the detail and the controls stay on the record.
for (const doctype of ["Hazard Assessment", "PFMEA"]) {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.is_new() || !frappe.model.can_create("Enterprise Risk")) return;
			frm.add_custom_button(
				__("Enterprise Risk"),
				() =>
					frappe
						.call(
							"foames.foames_risk.doctype.enterprise_risk.enterprise_risk.create_from_source",
							{ doctype: frm.doctype, name: frm.doc.name }
						)
						.then((r) => frappe.set_route("Form", "Enterprise Risk", r.message)),
				__("Create")
			);
		},
	});
}
