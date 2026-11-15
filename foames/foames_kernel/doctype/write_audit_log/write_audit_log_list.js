// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.listview_settings["Write Audit Log"] = {
	onload(listview) {
		if (!frappe.user.has_role(["System Manager", "FoaMES Quality"])) return;
		listview.page.add_inner_button(__("Verify Chain"), () =>
			frappe.call("foames.foames_kernel.write_gate.verify_audit_trail").then((r) => {
				const v = r.message || {};
				frappe.msgprint(
					v.intact
						? __("All {0} entries are intact.", [v.entries])
						: __("{0} of {1} entries do not match: {2}", [
								v.broken.length,
								v.entries,
								v.broken.join(", "),
							])
				);
			})
		);
	},
};
