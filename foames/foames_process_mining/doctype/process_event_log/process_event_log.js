// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Process Event Log", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Extract"), () => {
			frm.call("extract").then((r) => {
				const s = r.message || {};
				frappe.show_alert({
					message: __("{0} events in {1} cases, {2} variants", [s.events, s.cases, s.variants]),
					indicator: "green",
				});
				frm.reload_doc();
			});
		});
		if (frm.doc.status !== "Extracted") return;
		frm.add_custom_button(
			__("Discover"),
			() => {
				frm.call("discover", { min_edge_count: 1 }).then((r) => {
					const d = r.message || {};
					const edges = (d.dfg.edges || [])
						.slice(0, 40)
						.map(
							(e) =>
								`<tr><td>${frappe.utils.escape_html(e.from)}</td><td>${frappe.utils.escape_html(
									e.to
								)}</td><td class="text-right">${e.count}</td><td class="text-right">${
									e.median_seconds == null ? "" : frappe.format(e.median_seconds, { fieldtype: "Duration" })
								}</td></tr>`
						)
						.join("");
					const variants = (d.variants || [])
						.slice(0, 10)
						.map(
							(v) =>
								`<tr><td>${frappe.utils.escape_html(v.variant.join(" → "))}</td><td class="text-right">${
									v.cases
								}</td><td class="text-right">${(v.share * 100).toFixed(1)}%</td></tr>`
						)
						.join("");
					frappe.msgprint({
						title: __("Discovered process"),
						wide: true,
						message:
							`<h6>${__("Directly-follows graph")}</h6><table class="table table-bordered table-sm"><thead><tr><th>${__(
								"From"
							)}</th><th>${__("To")}</th><th>${__("Count")}</th><th>${__(
								"Median time"
							)}</th></tr></thead><tbody>${edges}</tbody></table>` +
							`<h6>${__("Variants")}</h6><table class="table table-bordered table-sm"><thead><tr><th>${__(
								"Path"
							)}</th><th>${__("Cases")}</th><th>${__("Share")}</th></tr></thead><tbody>${variants}</tbody></table>` +
							`<details><summary>${__("Graphviz DOT")}</summary><pre>${frappe.utils.escape_html(
								d.dot
							)}</pre></details>`,
					});
				});
			},
			__("Analyse")
		);
		frm.add_custom_button(
			__("Check against another log"),
			() => {
				frappe.prompt(
					{
						fieldname: "reference",
						fieldtype: "Link",
						options: "Process Event Log",
						label: __("Reference log"),
						reqd: 1,
					},
					(values) => {
						frm.call("check_against", { reference: values.reference }).then((r) => {
							const c = r.message || {};
							frappe.msgprint({
								title: __("Conformance"),
								message: __("{0} of {1} cases conform; fitness {2}", [
									c.conforming_cases,
									c.cases,
									(c.fitness || 0).toFixed(3),
								]),
							});
						});
					},
					__("Reference model")
				);
			},
			__("Analyse")
		);
		["xes", "ocel"].forEach((fmt) => {
			frm.add_custom_button(
				fmt.toUpperCase(),
				() => {
					frm.call("export_file", { fmt }).then((r) => {
						frm.reload_doc();
						window.open(r.message);
					});
				},
				__("Export")
			);
		});
	},
});
