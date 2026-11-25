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

frappe.ui.form.on("Cycle Time Standard", {
	setup(frm) {
		frm.set_query("operation_reference", () => ({ filters: { reference_type: "Operation" } }));
		frm.set_query("item_reference", () => ({ filters: { reference_type: "Item" } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Project Quantity"), () => {
			frappe.prompt(
				[
					{
						fieldname: "quantity",
						fieldtype: "Float",
						label: __("Quantity"),
						reqd: 1,
						default: 100,
					},
					{
						fieldname: "use_observed",
						fieldtype: "Check",
						label: __("Calibrate automatic time from the machine's last 30 days"),
						default: 0,
					},
				],
				(values) =>
					frappe
						.call("foames.foames_mes.cycle_time_api.project_time", {
							standard: frm.doc.name,
							quantity: values.quantity,
							use_observed: values.use_observed,
						})
						.then((r) => show_projection(r.message)),
				__("Project Time")
			);
		});
		if (frm.doc.machine) {
			frm.add_custom_button(__("Compare with Machine"), () =>
				frappe
					.call("foames.foames_mes.cycle_time_api.compare_with_observed", {
						standard: frm.doc.name,
					})
					.then((r) => show_comparison(r.message))
			);
		}
	},
});

function fmt(value, digits = 1) {
	return value === null || value === undefined ? "-" : Number(value).toFixed(digits);
}

function show_projection(p) {
	const rows = [
		[__("Cycles"), p.cycles],
		[__("Elapsed (min)"), fmt(p.elapsed_minutes)],
		[__("Automatic (min)"), fmt(p.automatic_minutes)],
		[__("Operator (min)"), fmt(p.operator_minutes)],
		[__("Batch time (min)"), fmt(p.setup_minutes)],
		[__("Parts per hour"), fmt(p.parts_per_hour)],
		[__("Cost per part"), fmt(p.cost_per_part, 2)],
	];
	const notes = (p.notes || []).map((n) => `<li>${frappe.utils.escape_html(n)}</li>`).join("");
	frappe.msgprint({
		title: __("Projection for {0}", [p.quantity]),
		message:
			`<table class="table table-bordered">${rows
				.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
				.join("")}</table>` + (notes ? `<ul>${notes}</ul>` : ""),
	});
}

function show_comparison(c) {
	const o = c.observed;
	const rows = [
		[__("Observed cycles"), fmt(o.cycles, 0)],
		[__("Automatic, standard (s)"), fmt(c.standard.automatic_seconds)],
		[__("Automatic, observed (s)"), fmt(o.automatic_seconds)],
		[__("Automatic variance (%)"), fmt(c.automatic_variance_percent)],
		[__("Cycle, standard (s)"), fmt(c.standard.cycle_seconds)],
		[__("Running plus idle per cycle, observed (s)"), fmt(o.cycle_seconds)],
		[__("Cycle variance (%)"), fmt(c.cycle_variance_percent)],
	];
	frappe.msgprint({
		title: __("Standard against the machine"),
		message: `<table class="table table-bordered">${rows
			.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
			.join("")}</table><p class="text-muted">${__(
			"Idle time includes waiting for material, so the observed cycle is an upper bound on the manual part."
		)}</p>`,
	});
}
