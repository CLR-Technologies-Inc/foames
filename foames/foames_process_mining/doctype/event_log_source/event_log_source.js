// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Log Source", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Preview events"), () => preview(frm));
	},
});

function cell(value) {
	return `<td>${frappe.utils.escape_html(String(value ?? ""))}</td>`;
}

function header(labels) {
	const cells = labels.map((label) => `<th>${__(label)}</th>`).join("");
	return `<thead><tr>${cells}</tr></thead>`;
}

function preview(frm) {
	frm.call("preview", { limit: 20 }).then((r) => {
		const data = r.message || {};
		if (!data.installed) {
			const msg = __("DocType {0} is not installed on this site", [frm.doc.source_doctype]);
			frappe.msgprint(msg);
			return;
		}
		const rows = (data.events || [])
			.map((e) => {
				const cells = [e.case_id, e.activity, e.lifecycle, e.timestamp, e.resource];
				return `<tr>${cells.map(cell).join("")}</tr>`;
			})
			.join("");
		const head = header(["Case", "Activity", "Lifecycle", "Time", "Resource"]);
		const body = `<tbody>${rows}</tbody>`;
		frappe.msgprint({
			title: __("{0} events", [data.total]),
			wide: true,
			message: `<table class="table table-bordered table-sm">${head}${body}</table>`,
		});
	});
}
