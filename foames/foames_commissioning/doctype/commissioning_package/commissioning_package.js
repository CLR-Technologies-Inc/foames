// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Commissioning Package", {
	refresh(frm) {
		if (frm.is_new()) return;
		const open = !["Handed Over", "Cancelled"].includes(frm.doc.status);
		if (open) {
			frm.add_custom_button(
				__("Test"),
				() => frappe.new_doc("Commissioning Test", { package: frm.doc.name }),
				__("Add")
			);
			frm.add_custom_button(
				__("Loop Check"),
				() => frappe.new_doc("Loop Check", { package: frm.doc.name }),
				__("Add")
			);
		}
		frm.add_custom_button(
			__("Punch Item"),
			() => frappe.new_doc("Punch Item", { package: frm.doc.name }),
			__("Add")
		);
		frm.add_custom_button(__("Punch List"), () =>
			frappe.set_route("query-report", "Punch List", { package: frm.doc.name })
		);
		if (!open) return;
		const user = frappe.session.user;
		for (const [side, acceptor, accepted] of [
			["operations", "operations_acceptor", "operations_accepted_on"],
			["maintenance", "maintenance_acceptor", "maintenance_accepted_on"],
		]) {
			if (frm.doc[acceptor] === user && !frm.doc[accepted]) {
				frm.add_custom_button(__("Accept for {0}", [__(side)]), () =>
					frm.call("accept", { side }).then(() => frm.reload_doc())
				);
			}
		}
		if (frm.doc.status === "Ready for Handover") {
			frm.add_custom_button(__("Hand Over"), () =>
				frappe.confirm(__("Hand the equipment over to operations and maintenance?"), () =>
					frm.call("hand_over").then(() => frm.reload_doc())
				)
			).addClass("btn-primary");
		}
		if (frm.doc.blocker_count) {
			frm.dashboard.set_headline(
				__("{0} items block the handover. See Handover Blockers.", [
					frm.doc.blocker_count,
				]),
				"orange"
			);
		}
	},
});
