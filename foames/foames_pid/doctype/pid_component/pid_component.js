// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("PID Component", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.drawing) {
			frm.add_custom_button(__("Show on drawing"), () =>
				frappe.set_route("pid-viewer", { drawing: frm.doc.drawing, tag: frm.doc.name })
			);
		}
		if (frm.doc.machine && frm.doc.signal_name) {
			frappe.call("foames.foames_pid.api.get_component", { tag: frm.doc.name }).then((r) => {
				const live = (r.message || {}).live || {};
				if (live.value === null || live.value === undefined) {
					frm.dashboard.set_headline(
						__("No value has been recorded for this signal yet.")
					);
					return;
				}
				const flag = live.flag ? ` (${__(live.flag)})` : "";
				frm.dashboard.set_headline(
					__("Last value {0} {1} at {2}{3}", [
						live.value,
						frappe.utils.escape_html(live.unit || ""),
						live.at,
						flag,
					])
				);
			});
		}
	},
});
