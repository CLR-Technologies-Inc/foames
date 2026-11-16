// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

frappe.listview_settings["Pending Write"] = {
	get_indicator(doc) {
		const colors = {
			"Awaiting Sign-off": "orange",
			Approved: "blue",
			Released: "green",
			Executed: "green",
			Rejected: "red",
			Blocked: "red",
			Failed: "red",
			Withdrawn: "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
