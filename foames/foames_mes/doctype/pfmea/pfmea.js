// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("PFMEA", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Observe Floor Now"), () =>
				frappe
					.call("foames.foames_mes.doctype.pfmea.pfmea.observe_now", {
						name: frm.doc.name,
					})
					.then((r) => {
						const m = r.message || {};
						frappe.show_alert({
							message: __(
								"{0} rows observed: {1} above their occurrence rating, {2} SPC signals",
								[m.rows, m.above_rating, m.spc_signals]
							),
							indicator: m.above_rating || m.spc_signals ? "orange" : "green",
						});
						frm.reload_doc();
					})
			);
		}
		frm.add_custom_button(
			__("Control Plan"),
			() => frappe.set_route("query-report", "PFMEA Control Plan", { pfmea: frm.doc.name }),
			__("View")
		);
		frm.add_custom_button(
			__("Risk Register"),
			() => frappe.set_route("query-report", "PFMEA Risk Register", { pfmea: frm.doc.name }),
			__("View")
		);
	},
});
