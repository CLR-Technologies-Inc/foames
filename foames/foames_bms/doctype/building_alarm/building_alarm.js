// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Building Alarm", {
	refresh(frm) {
		if (["Active", "Returned"].includes(frm.doc.status) && frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Acknowledge"), () => {
				frappe.prompt(
					{ fieldname: "note", fieldtype: "Small Text", label: __("Note") },
					(values) =>
						frappe
							.call(
								"foames.foames_bms.doctype.building_alarm.building_alarm.acknowledge",
								{ alarm: frm.doc.name, note: values.note }
							)
							.then(() => frm.reload_doc()),
					__("Acknowledge alarm")
				);
			});
		}
	},
});
