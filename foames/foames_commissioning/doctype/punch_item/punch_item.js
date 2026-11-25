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

frappe.ui.form.on("Punch Item", {
	refresh(frm) {
		if (frm.doc.source_doctype && frm.doc.source_name) {
			frm.add_custom_button(__("Raised From"), () =>
				frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name)
			);
		}
	},
	category(frm) {
		if (frm.doc.category === "A" && frm.doc.deferred) frm.set_value("deferred", 0);
	},
});
