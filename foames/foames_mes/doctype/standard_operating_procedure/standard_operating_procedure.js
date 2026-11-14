// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

const SOP_METHOD =
	"foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure.";

function sop_call(frm, method, args) {
	return frappe
		.call({ method: SOP_METHOD + method, args: { name: frm.doc.name, ...(args || {}) } })
		.then((r) => {
			frm.reload_doc();
			return r.message;
		});
}

function sop_prompt(frm, method, label, title, required) {
	frappe.prompt(
		[{ fieldname: "text", fieldtype: "Small Text", label: label, reqd: required ? 1 : 0 }],
		(values) => {
			const key = method === "retire" ? "reason" : "comment";
			sop_call(frm, method, { [key]: values.text });
		},
		title,
	);
}

frappe.ui.form.on("Standard Operating Procedure", {
	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.status;
		const can_write = frm.perm[0] && frm.perm[0].write;
		if (status !== "Draft") frm.disable_save();

		if (status === "Draft" && can_write) {
			frm.add_custom_button(__("Send for Review"), () =>
				sop_call(frm, "submit_for_review"),
			).addClass("btn-primary");
		}
		if (status === "In Review") {
			frm.add_custom_button(__("Sign"), () =>
				sop_prompt(frm, "sign", __("Comment"), __("Sign this revision"), false),
			).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () =>
				sop_prompt(frm, "reject", __("Reason"), __("Send back to Draft"), true),
			);
		}
		if (status === "Effective") {
			frm.add_custom_button(
				__("Acknowledge"),
				() => sop_call(frm, "acknowledge"),
				__("Training"),
			);
			if (can_write) {
				frm.add_custom_button(
					__("Record Training"),
					() =>
						frappe.prompt(
							[
								{
									fieldname: "user",
									fieldtype: "Link",
									options: "User",
									label: __("User"),
									reqd: 1,
								},
								{
									fieldname: "method",
									fieldtype: "Select",
									label: __("Method"),
									options: ["Trained", "Trained and Assessed"],
									default: "Trained",
									reqd: 1,
								},
								{ fieldname: "note", fieldtype: "Small Text", label: __("Note") },
							],
							(values) => sop_call(frm, "record_training", values),
							__("Record Training"),
						),
					__("Training"),
				);
				frm.add_custom_button(__("Record Periodic Review"), () =>
					sop_prompt(frm, "record_review", __("Comment"), __("Still current"), false),
				);
			}
		}
		if (["Effective", "Approved"].includes(status) && can_write) {
			frm.add_custom_button(__("New Revision"), () =>
				frappe
					.call({ method: SOP_METHOD + "new_revision", args: { name: frm.doc.name } })
					.then((r) =>
						frappe.set_route("Form", "Standard Operating Procedure", r.message),
					),
			);
		}
		if (["Draft", "Approved", "Effective"].includes(status) && can_write) {
			frm.add_custom_button(__("Retire"), () =>
				sop_prompt(frm, "retire", __("Reason"), __("Retire this SOP"), true),
			);
		}
		const colour = {
			Draft: "gray",
			"In Review": "orange",
			Approved: "blue",
			Effective: "green",
			Superseded: "darkgrey",
			Obsolete: "red",
		}[status];
		if (colour) frm.page.set_indicator(__(status), colour);
	},
});
