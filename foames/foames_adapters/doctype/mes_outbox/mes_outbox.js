// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("MES Outbox", {
	refresh(frm) {
		if (frm.doc.status === "Failed" || (frm.doc.status === "Unknown" && frm.doc.needs_check)) {
			frm.add_custom_button(__("Requeue"), () => {
				frm.call("requeue").then(() => frm.reload_doc());
			});
		}
		if (frm.doc.status === "Unknown" && frm.doc.needs_check) {
			frm.add_custom_button(__("Mark Posted"), () => {
				frappe.prompt(
					{
						fieldname: "document",
						fieldtype: "Data",
						label: __("Record in the MES"),
						description: __(
							"The id of the record the send created, if you found one."
						),
					},
					(values) => {
						frm.call("mark_posted", { document: values.document }).then(() =>
							frm.reload_doc()
						);
					},
					__("A person has checked the system"),
					__("Mark Posted")
				);
			});
		}
		if (!["Posted", "Sending", "Cancelled"].includes(frm.doc.status) && !frm.is_new()) {
			frm.add_custom_button(__("Cancel Posting"), () => {
				const message = __("Drop this posting? Later ones in its group are then sent.");
				frappe.confirm(message, () => {
					frm.call("cancel_posting").then(() => frm.reload_doc());
				});
			});
		}
	},
});
