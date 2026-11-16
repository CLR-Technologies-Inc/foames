// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.ui.form.on("Phase Review", {
	setup(frm) {
		frm.set_query("npi_program", () => ({
			filters: {
				status: ["in", ["Active", "On Hold"]],
				phase_review_board: ["is", "set"],
			},
		}));
	},
});
