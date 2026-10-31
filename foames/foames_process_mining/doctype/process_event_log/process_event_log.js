// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Process Event Log", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Extract"), () => extract(frm));
		if (frm.doc.status !== "Extracted") return;
		frm.add_custom_button(__("Discover"), () => discover(frm), __("Analyse"));
		frm.add_custom_button(__("Check against another log"), () => check(frm), __("Analyse"));
		["xes", "ocel"].forEach((fmt) => {
			frm.add_custom_button(fmt.toUpperCase(), () => exportLog(frm, fmt), __("Export"));
		});
	},
});

function cell(value, right) {
	const text = frappe.utils.escape_html(String(value ?? ""));
	return right ? `<td class="text-right">${text}</td>` : `<td>${text}</td>`;
}

function table(title, labels, rows) {
	const head = labels.map((label) => `<th>${__(label)}</th>`).join("");
	const body = rows.join("");
	return `<h6>${__(title)}</h6><table class="table table-bordered table-sm">
		<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function duration(seconds) {
	if (seconds == null) return "";
	return frappe.format(seconds, { fieldtype: "Duration" });
}

function extract(frm) {
	frm.call("extract").then((r) => {
		const s = r.message || {};
		const counts = [s.events, s.cases, s.variants];
		const message = __("{0} events in {1} cases, {2} variants", counts);
		frappe.show_alert({ message, indicator: "green" });
		frm.reload_doc();
	});
}

function discover(frm) {
	frm.call("discover", { min_edge_count: 1 }).then((r) => {
		const d = r.message || {};
		const edges = (d.dfg.edges || []).slice(0, 40).map((e) => {
			const time = duration(e.median_seconds);
			const cells = [cell(e.from), cell(e.to), cell(e.count, true), cell(time, true)];
			return `<tr>${cells.join("")}</tr>`;
		});
		const variants = (d.variants || []).slice(0, 10).map((v) => {
			const share = (v.share * 100).toFixed(1) + "%";
			const cells = [cell(v.variant.join(" → ")), cell(v.cases, true), cell(share, true)];
			return `<tr>${cells.join("")}</tr>`;
		});
		const dot = frappe.utils.escape_html(d.dot);
		frappe.msgprint({
			title: __("Discovered process"),
			wide: true,
			message:
				table("Directly-follows graph", ["From", "To", "Count", "Median time"], edges) +
				table("Variants", ["Path", "Cases", "Share"], variants) +
				`<details><summary>${__("Graphviz DOT")}</summary><pre>${dot}</pre></details>`,
		});
	});
}

function check(frm) {
	const field = {
		fieldname: "reference",
		fieldtype: "Link",
		options: "Process Event Log",
		label: __("Reference log"),
		reqd: 1,
	};
	frappe.prompt(
		field,
		(values) => {
			frm.call("check_against", { reference: values.reference }).then((r) => {
				const c = r.message || {};
				const values = [c.conforming_cases, c.cases, (c.fitness || 0).toFixed(3)];
				frappe.msgprint({
					title: __("Conformance"),
					message: __("{0} of {1} cases conform; fitness {2}", values),
				});
			});
		},
		__("Reference model")
	);
}

function exportLog(frm, fmt) {
	frm.call("export_file", { fmt }).then((r) => {
		frm.reload_doc();
		window.open(r.message);
	});
}
