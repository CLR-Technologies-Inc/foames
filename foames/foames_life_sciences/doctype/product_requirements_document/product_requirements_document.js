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

frappe.ui.form.on("Product Requirements Document", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Trace Matrix"), () => {
			frm.call("get_trace_matrix").then((r) => {
				const t = r.message;
				const esc = frappe.utils.escape_html;
				const rows = t.matrix
					.map(
						(m) =>
							`<tr><td>${esc(m.req_id)}</td><td>${__(m.level)}</td><td>${esc(
								m.parent || ""
							)}</td>` +
							`<td>${esc(m.design_output || "")}</td><td>${esc(
								m.verification_reference || ""
							)}</td>` +
							`<td>${__(m.verification_status)}</td><td>${esc(
								m.validation_reference || ""
							)}</td>` +
							`<td>${m.gaps.map(esc).join("; ")}</td></tr>`
					)
					.join("");
				const d = new frappe.ui.Dialog({ title: __("Trace Matrix"), size: "extra-large" });
				d.$body.html(
					`<p>${__("Verified")}: ${t.percent_verified}% &middot; ${__("Refined")}: ${
						t.percent_refined
					}% &middot; ` +
						`${__("Critical open")}: ${
							t.critical_open.map(esc).join(", ") || __("none")
						}</p>` +
						`<table class="table table-bordered table-sm"><tr><th>${__(
							"ID"
						)}</th><th>${__("Level")}</th>` +
						`<th>${__("Refines")}</th><th>${__("Design Output")}</th><th>${__(
							"Verification"
						)}</th>` +
						`<th>${__("Status")}</th><th>${__("Validation")}</th><th>${__(
							"Gaps"
						)}</th></tr>${rows}</table>`
				);
				d.show();
			});
		});
	},
});
