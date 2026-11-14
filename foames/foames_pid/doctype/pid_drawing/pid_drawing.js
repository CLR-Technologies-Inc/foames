// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("PID Drawing", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open in P&ID Viewer"), () =>
			frappe.set_route("pid-viewer", { drawing: frm.doc.name })
		);
		if (frm.doc.source_format === "DEXPI" && frm.doc.source_file && frm.perm[0].write) {
			frm.add_custom_button(__("Import DEXPI"), () => {
				frm.call({ method: "import_dexpi", doc: frm.doc, freeze: true }).then((r) => {
					const s = r.message || {};
					frappe.msgprint({
						title: __("DEXPI imported"),
						indicator: "green",
						message: __("{0} created, {1} updated. {2} warnings.", [
							(s.created || []).length,
							(s.updated || []).length,
							(s.warnings || []).length,
						]),
					});
					frm.reload_doc();
				});
			});
		}
		frm.add_custom_button(
			__("Suggest signal links"),
			() => pid_suggest_links(frm.doc.name),
			__("Tags")
		);
		frm.add_custom_button(
			__("Export tag register"),
			() => pid_export_register(frm.doc.name),
			__("Tags")
		);
		frm.add_custom_button(
			__("Components"),
			() => frappe.set_route("List", "PID Component", { drawing: frm.doc.name }),
			__("Tags")
		);
	},
});

function pid_export_register(drawing) {
	frappe.call("foames.foames_pid.api.export_tag_register", { drawing }).then((r) => {
		const blob = new Blob([r.message || ""], { type: "text/csv" });
		const a = document.createElement("a");
		a.href = URL.createObjectURL(blob);
		a.download = `${drawing || "tag-register"}.csv`;
		a.click();
		URL.revokeObjectURL(a.href);
	});
}

function pid_suggest_links(drawing) {
	frappe.call("foames.foames_pid.api.suggest_links", { drawing }).then((r) => {
		const links = r.message || [];
		if (!links.length) {
			frappe.msgprint(__("No new links to suggest. Tags already linked are left out."));
			return;
		}
		const esc = frappe.utils.escape_html;
		const rows = links
			.map(
				(l, i) => `<tr>
					<td><input type="checkbox" data-i="${i}" checked></td>
					<td><b>${esc(l.tag)}</b></td>
					<td>${esc(l.machine)}</td>
					<td>${esc(l.event_type || "")} ${esc(l.signal_name || "")}</td>
					<td><small>${esc(l.reason)}</small></td>
				</tr>`
			)
			.join("");
		const d = new frappe.ui.Dialog({
			title: __("Suggested signal links"),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "table" }],
			primary_action_label: __("Apply selected"),
			primary_action() {
				const chosen = [];
				d.$wrapper.find("input[data-i]:checked").each(function () {
					chosen.push(links[$(this).data("i")]);
				});
				frappe.call("foames.foames_pid.api.apply_links", { links: chosen }).then((res) => {
					frappe.show_alert({
						message: __("{0} tags linked", [(res.message || []).length]),
						indicator: "green",
					});
					d.hide();
				});
			},
		});
		const head = [__("Tag"), __("Machine"), __("Signal"), __("Why")]
			.map((label) => `<th>${label}</th>`)
			.join("");
		d.fields_dict.table.$wrapper.html(
			`<table class="table table-sm"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table>`
		);
		d.show();
	});
}
