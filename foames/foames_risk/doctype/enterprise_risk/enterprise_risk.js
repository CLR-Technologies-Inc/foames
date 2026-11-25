// Copyright 2026 CLR Technologies Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

const RISK_METHODS = "foames.foames_risk.doctype.enterprise_risk.enterprise_risk";

frappe.ui.form.on("Enterprise Risk", {
	setup(frm) {
		frappe.call(`${RISK_METHODS}.get_linkable_doctypes`).then((r) => {
			const names = r.message || [];
			const query = () => ({ filters: { name: ["in", names] } });
			frm.set_query("link_doctype", "links", query);
			frm.set_query("evidence_doctype", "controls", query);
		});
		frm.set_query("category", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		if (frm.is_new()) {
			frm.add_custom_button(__("Start from Template"), () => pick_template(frm));
			return;
		}
		if (frm.doc.status !== "Closed") {
			frm.add_custom_button(__("Record Review"), () =>
				frappe.prompt(
					[{ fieldname: "notes", fieldtype: "Small Text", label: __("Review Notes") }],
					(values) =>
						frappe
							.call(`${RISK_METHODS}.record_review`, {
								name: frm.doc.name,
								notes: values.notes,
							})
							.then(() => frm.reload_doc()),
					__("Record Review"),
					__("Record")
				)
			);
			const can_accept =
				frappe.user.has_role("FoaMES Supervisor") ||
				frappe.user.has_role("System Manager");
			const accepted =
				frm.doc.accepted_by && frm.doc.accepted_score === frm.doc.residual_score;
			if (can_accept && !accepted) {
				frm.add_custom_button(__("Accept Residual Risk"), () =>
					frappe.prompt(
						[
							{
								fieldname: "justification",
								fieldtype: "Small Text",
								label: __("Why the Residual Risk Is Accepted"),
								reqd: 1,
								default: frm.doc.acceptance_justification,
							},
						],
						(values) =>
							frappe
								.call(`${RISK_METHODS}.accept_residual_risk`, {
									name: frm.doc.name,
									justification: values.justification,
								})
								.then(() => frm.reload_doc()),
						__("Accept at score {0}", [frm.doc.residual_score]),
						__("Accept")
					)
				);
			}
		}
		frm.add_custom_button(
			__("Register"),
			() =>
				frappe.set_route("query-report", "Risk Register", { category: frm.doc.category }),
			__("View")
		);
		frm.add_custom_button(
			__("Heat Map"),
			() => frappe.set_route("query-report", "Risk Heat Map"),
			__("View")
		);
		if (!frm.doc.within_tolerance && !frm.doc.accepted_by) {
			frm.dashboard.set_headline(
				__("Residual risk {0} is above the {1} tolerance.", [
					frm.doc.residual_rating,
					frm.doc.tolerance,
				]),
				"orange"
			);
		}
	},
});

function pick_template(frm) {
	frappe.prompt(
		[
			{
				fieldname: "template",
				fieldtype: "Link",
				options: "Risk Template",
				label: __("Risk Template"),
				reqd: 1,
				get_query: () => ({ filters: { disabled: 0 } }),
			},
		],
		(values) =>
			frappe
				.call(`${RISK_METHODS}.create_from_template`, {
					template: values.template,
					machine: frm.doc.machine,
				})
				.then((r) => frappe.set_route("Form", "Enterprise Risk", r.message)),
		__("Start from Template"),
		__("Create")
	);
}
