// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

const WI_METHODS = "foames.foames_mes.doctype.work_instruction.work_instruction";
const WI_RELEASE_ROLES = ["FoaMES Engineer", "FoaMES Quality", "System Manager"];

frappe.ui.form.on("Work Instruction", {
	refresh(frm) {
		if (frm.is_new()) return;
		const can_release = WI_RELEASE_ROLES.some((role) => frappe.user.has_role(role));
		if (frm.doc.status === "Draft" && frm.perm[0].write && can_release) {
			frm.add_custom_button(__("Release"), () => {
				frappe.confirm(
					__(
						"Release revision {0}? It can no longer be edited, and the revision of {1} in use becomes Obsolete.",
						[frm.doc.revision, frm.doc.instruction_code]
					),
					() =>
						frappe
							.call({
								method: `${WI_METHODS}.release`,
								args: { name: frm.doc.name },
							})
							.then(() => frm.reload_doc())
				);
			}).addClass("btn-primary");
		}
		if (frm.doc.status !== "Draft" && frappe.model.can_create("Work Instruction")) {
			frm.add_custom_button(__("New Revision"), () => {
				frappe.prompt(
					{
						fieldname: "change_note",
						label: __("What Changes"),
						fieldtype: "Small Text",
					},
					(values) =>
						frappe
							.call({
								method: `${WI_METHODS}.new_revision`,
								args: { name: frm.doc.name, change_note: values.change_note },
							})
							.then((r) =>
								frappe.set_route("Form", "Work Instruction", r.message.name)
							),
					__("New Revision of {0}", [frm.doc.instruction_code])
				);
			});
		}
		if (frm.doc.status === "Released" && frm.perm[0].write) {
			frm.add_custom_button(__("Make Obsolete"), () =>
				frappe
					.call({ method: `${WI_METHODS}.make_obsolete`, args: { name: frm.doc.name } })
					.then(() => frm.reload_doc())
			);
		}
		if (frm.doc.status !== "Draft") {
			frm.set_intro(
				__("Revision {0} is {1} and cannot be edited. Use New Revision to change it.", [
					frm.doc.revision,
					__(frm.doc.status),
				])
			);
			frm.disable_form();
		}
	},
});
