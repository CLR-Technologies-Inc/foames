// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Material Queue", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Dispatch list"), () =>
			frappe
				.call("foames.foames_mes.api.get_dispatch_list", { queue: frm.doc.name })
				.then((r) => {
					const rows = (r.message || [])
						.map(
							(e, i) =>
								`<tr><td>${i + 1}</td><td>${frappe.utils.escape_html(e.name)}</td><td>${frappe.utils.escape_html(e.item || "")}</td><td>${e.quantity || ""} ${frappe.utils.escape_html(e.uom || "")}</td><td>${frappe.utils.escape_html(e.state)}</td></tr>`
						)
						.join("");
					frappe.msgprint({
						title: __("Next to start ({0})", [frm.doc.discipline]),
						message: rows
							? `<table class="table table-sm"><tr><th>#</th><th>${__("Entry")}</th><th>${__("Item")}</th><th>${__("Quantity")}</th><th>${__("State")}</th></tr>${rows}</table>`
							: __("Nothing is ready to start."),
					});
				})
		);
		frm.add_custom_button(__("Entries"), () =>
			frappe.set_route("List", "Material Queue Entry", { queue: frm.doc.name })
		);
	},
});
