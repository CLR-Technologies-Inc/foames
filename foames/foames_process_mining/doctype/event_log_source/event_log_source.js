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
				return `<tr>${cells.map((c) => cell(c)).join("")}</tr>`;
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
