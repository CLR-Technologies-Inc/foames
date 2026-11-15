// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

function record_decision(frm) {
	const d = new frappe.ui.Dialog({
		title: __("{0} gate", [__(frm.doc.current_stage)]),
		fields: [
			{
				fieldname: "decision",
				fieldtype: "Select",
				label: __("Decision"),
				options: ["Go", "Conditional Go", "Recycle", "Hold", "Kill"],
				reqd: 1,
			},
			{
				fieldname: "conditions",
				fieldtype: "Small Text",
				label: __("Conditions or Rationale"),
			},
			{
				fieldname: "conditions_due",
				fieldtype: "Date",
				label: __("Conditions Due"),
				depends_on: "eval:doc.decision=='Conditional Go'",
			},
		],
		primary_action_label: __("Record"),
		primary_action(values) {
			frm.call("record_gate_decision", values).then(() => {
				d.hide();
				frm.reload_doc();
			});
		},
	});
	d.show();
}

frappe.ui.form.on("NPI Program", {
	refresh(frm) {
		if (frm.is_new() || ["Launched", "Cancelled"].includes(frm.doc.status)) return;
		if (frm.doc.phase_review_board) {
			frm.add_custom_button(__("New Phase Review"), () =>
				frappe.new_doc("Phase Review", { npi_program: frm.doc.name })
			);
		} else {
			frm.add_custom_button(__("Record Gate Decision"), () => record_decision(frm));
		}
		const open = (frm.doc.gates || []).filter(
			(g) => g.decision === "Conditional Go" && !g.conditions_closed
		);
		open.forEach((g) =>
			frm.add_custom_button(
				__("Close {0} Conditions", [__(g.stage)]),
				() =>
					frm
						.call("close_gate_conditions", { stage: g.stage })
						.then(() => frm.reload_doc()),
				__("Gates")
			)
		);
		frm.call("get_stage_progress").then((r) => {
			const rows = (r.message || [])
				.map(
					(s) =>
						`<tr><td>${__(s.stage)}</td><td>${s.done} / ${s.deliverables}</td><td>${
							s.missing_required.length
						}</td></tr>`
				)
				.join("");
			frm.dashboard.set_headline_alert(
				`<table class="table table-sm"><tr><th>${__("Stage")}</th><th>${__(
					"Done"
				)}</th><th>${__("Required open")}</th></tr>${rows}</table>`
			);
		});
	},
});
