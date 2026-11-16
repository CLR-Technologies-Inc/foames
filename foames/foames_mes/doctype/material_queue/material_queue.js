// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Material Queue", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Dispatch list"), () =>
			frappe
				.call("foames.foames_mes.api.get_dispatch_list", { queue: frm.doc.name })
				.then((r) => {
					const esc = frappe.utils.escape_html;
					const cell = (value) => `<td>${esc(value == null ? "" : String(value))}</td>`;
					const head = ["#", __("Entry"), __("Item"), __("Quantity"), __("State")]
						.map((label) => `<th>${esc(label)}</th>`)
						.join("");
					const rows = (r.message || [])
						.map((e, i) => {
							const quantity = `${e.quantity || ""} ${e.uom || ""}`;
							const cells = [i + 1, e.name, e.item, quantity, e.state].map(cell);
							return `<tr>${cells.join("")}</tr>`;
						})
						.join("");
					const table = `<table class="table table-sm"><tr>${head}</tr>${rows}</table>`;
					frappe.msgprint({
						title: __("Next to start ({0})", [frm.doc.discipline]),
						message: rows ? table : __("Nothing is ready to start."),
					});
				})
		);
		frm.add_custom_button(__("Entries"), () =>
			frappe.set_route("List", "Material Queue Entry", { queue: frm.doc.name })
		);
	},
});
