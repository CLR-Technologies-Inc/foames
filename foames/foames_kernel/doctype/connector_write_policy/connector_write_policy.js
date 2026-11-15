// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Connector Write Policy", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Pending Writes"), () =>
			frappe.set_route("List", "Pending Write", { connector: frm.doc.connector })
		);
		frm.add_custom_button(__("Audit Log"), () =>
			frappe.set_route("List", "Write Audit Log", { connector: frm.doc.connector })
		);
		frm.dashboard.set_headline(
			frm.doc.read_only
				? __("Read-only: writes wait for sign-off or are refused.")
				: __("Read-write, unless site-wide read-only mode is on in FoaMES Settings.")
		);
	},
});
