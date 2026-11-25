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

frappe.ui.form.on("Connector Write Policy", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Pending Writes"), () =>
			frappe.set_route("List", "Pending Write", { connector: frm.doc.connector })
		);
		frm.add_custom_button(__("Audit Log"), () =>
			frappe.set_route("List", "Write Audit Log", { connector: frm.doc.connector })
		);
		frm.dashboard.set_headline(
			frm.doc.read_only
				? __("Read-only: writes wait for sign-off or are refused.")
				: __("Read-write, unless site-wide read-only mode is on in FoaMES Settings.")
		);
	},
});
