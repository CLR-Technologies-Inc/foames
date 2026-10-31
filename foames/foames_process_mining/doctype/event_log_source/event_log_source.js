// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Log Source", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Preview events"), () => {
			frm.call("preview", { limit: 20 }).then((r) => {
				const data = r.message || {};
				if (!data.installed) {
					frappe.msgprint(__("DocType {0} is not installed on this site", [frm.doc.source_doctype]));
					return;
				}
				const rows = (data.events || [])
					.map(
						(e) =>
							`<tr><td>${frappe.utils.escape_html(e.case_id)}</td><td>${frappe.utils.escape_html(
								e.activity
							)}</td><td>${frappe.utils.escape_html(e.lifecycle)}</td><td>${frappe.utils.escape_html(
								e.timestamp
							)}</td><td>${frappe.utils.escape_html(e.resource || "")}</td></tr>`
					)
					.join("");
				frappe.msgprint({
					title: __("{0} events", [data.total]),
					wide: true,
					message: `<table class="table table-bordered table-sm"><thead><tr><th>${__("Case")}</th><th>${__(
						"Activity"
					)}</th><th>${__("Lifecycle")}</th><th>${__("Time")}</th><th>${__(
						"Resource"
					)}</th></tr></thead><tbody>${rows}</tbody></table>`,
				});
			});
		});
	},
});
