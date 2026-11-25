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

frappe.ui.form.on("PD Simulation Study", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Generate Design"),
			() => {
				const go = (overwrite) =>
					frm.call("generate_design", { overwrite }).then(() => frm.reload_doc());
				const has_results = (frm.doc.runs || []).some((r) => r.y1 || r.y2 || r.y3 || r.y4);
				if (has_results) {
					frappe.confirm(__("Replace the runs and their results?"), () => go(1));
				} else {
					go(0);
				}
			},
			__("Study")
		);
		frm.add_custom_button(
			__("Fit Models"),
			() => frm.call("fit_models").then(() => frm.reload_doc()),
			__("Study")
		);
		if (!frm.doc.model_results) return;
		frm.add_custom_button(
			__("Run What-If"),
			() => frm.call("run_what_if").then(() => frm.reload_doc()),
			__("Study")
		);
		frm.add_custom_button(
			__("Design Space"),
			() => {
				const names = (frm.doc.factors || []).map((f) => f.factor);
				const d = new frappe.ui.Dialog({
					title: __("Design Space"),
					fields: [
						{
							fieldname: "x_factor",
							fieldtype: "Select",
							label: __("X Factor"),
							options: names,
							reqd: 1,
							default: names[0],
						},
						{
							fieldname: "y_factor",
							fieldtype: "Select",
							label: __("Y Factor"),
							options: names,
							reqd: 1,
							default: names[1],
						},
						{ fieldname: "steps", fieldtype: "Int", label: __("Steps"), default: 21 },
						{ fieldname: "out", fieldtype: "HTML" },
					],
					primary_action_label: __("Map"),
					primary_action(values) {
						frm.call("get_design_space", values).then((r) => {
							const s = r.message;
							const cells = s.grid
								.slice()
								.reverse()
								.map(
									(row, i) =>
										`<tr><th>${frappe.format(
											s.y_values[s.y_values.length - 1 - i],
											{ fieldtype: "Float" }
										)}</th>` +
										row
											.map(
												(v) =>
													`<td style="background:${
														v ? "var(--green-200)" : "var(--red-100)"
													};width:12px"></td>`
											)
											.join("") +
										"</tr>"
								)
								.join("");
							d.fields_dict.out.$wrapper.html(
								`<p>${__("Inside")}: ${s.percent_inside.toFixed(
									1
								)}% (${frappe.utils.escape_html(s.y_factor)} ${__("up")}, ` +
									`${frappe.utils.escape_html(s.x_factor)} ${__("across")} ${
										s.x_values[0]
									} to ${s.x_values[s.x_values.length - 1]})</p>` +
									`<table class="table-sm">${cells}</table>`
							);
						});
					},
				});
				d.show();
			},
			__("Study")
		);
	},
});
