// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Pending Write", {
	refresh(frm) {
		const colors = {
			"Awaiting Sign-off": "orange",
			Approved: "blue",
			Released: "green",
			Executed: "green",
			Rejected: "red",
			Blocked: "red",
			Failed: "red",
			Withdrawn: "gray",
		};
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "gray");
		frm.add_custom_button(__("Audit Log"), () =>
			frappe.set_route("List", "Write Audit Log", { pending_write: frm.doc.name })
		);
		frm.add_custom_button(__("Verify Seal"), () =>
			frappe
				.call("foames.foames_kernel.write_gate.verify_pending_write", {
					pending_write: frm.doc.name,
				})
				.then((r) => {
					const v = r.message || {};
					const sig =
						v.signature_ok === null
							? __("not signed")
							: v.signature_ok
							? __("intact")
							: __("DOES NOT MATCH");
					frappe.msgprint(
						__("Payload: {0}. Signature: {1}.", [
							v.payload_ok ? __("intact") : __("DOES NOT MATCH"),
							sig,
						])
					);
				})
		);
		if (frm.doc.status === "Awaiting Sign-off") {
			frm.add_custom_button(__("Sign Off"), () => sign(frm)).addClass("btn-primary");
		}
	},
});

function sign(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Electronic signature"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${__(
					"You are signing {0}: {1}. Your name, the time, the meaning and your reason are recorded with this write and in the audit log.",
					[
						frappe.utils.escape_html(frm.doc.name),
						frappe.utils.escape_html(frm.doc.summary || frm.doc.action),
					]
				)}</p>`,
			},
			{
				fieldname: "meaning",
				fieldtype: "Select",
				label: __("Meaning"),
				options: "Approved\nRejected",
				default: "Approved",
				reqd: 1,
			},
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
			{
				fieldname: "password",
				fieldtype: "Password",
				label: __("Your password"),
				reqd: 1,
				description: __("Re-enter your password to sign as {0}.", [
					frappe.session.user_fullname,
				]),
			},
		],
		primary_action_label: __("Sign"),
		primary_action(values) {
			frappe
				.call({
					method: "foames.foames_kernel.write_gate.sign_pending_write",
					args: { pending_write: frm.doc.name, ...values },
					freeze: true,
				})
				.then(() => {
					dialog.hide();
					frm.reload_doc();
				});
		},
	});
	dialog.show();
}
