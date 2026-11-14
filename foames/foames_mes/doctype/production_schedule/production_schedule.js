// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Production Schedule", {
	refresh(frm) {
		if (frm.is_new()) return;
		const can_write = frm.perm[0] && frm.perm[0].write;
		if (frm.doc.status === "Draft" && can_write) {
			frm.add_custom_button(
				__("Get Operations"),
				() => frm.call("get_operations", { replace: 1 }).then(() => frm.reload_doc()),
				__("Plan")
			);
			frm.add_custom_button(
				__("Build"),
				() =>
					frm.call("build").then((r) => {
						frm.reload_doc();
						const k = r.message || {};
						frappe.show_alert({
							message: __("{0} scheduled, {1} unscheduled, {2} late jobs", [
								k.scheduled,
								k.unscheduled,
								(k.late_jobs || []).length,
							]),
							indicator:
								k.unscheduled || (k.late_jobs || []).length ? "orange" : "green",
						});
					}),
				__("Plan")
			);
			if (frm.doc.built_on) {
				frm.add_custom_button(
					__("Publish"),
					() =>
						frappe.confirm(
							__(
								"Publish this schedule? The one published before it for the same line is superseded."
							),
							() => frm.call("publish").then(() => frm.reload_doc())
						),
					__("Plan")
				);
			}
		}
		if (frm.doc.status !== "Draft" && frappe.model.can_create("Production Schedule")) {
			frm.add_custom_button(__("Copy to New Draft"), () =>
				frm
					.call("copy_to_draft")
					.then((r) => frappe.set_route("Form", "Production Schedule", r.message))
			);
		}
		if (frm.doc.built_on) {
			frm.add_custom_button(__("Gantt"), () => {
				frappe.route_options = { production_schedule: frm.doc.name };
				frappe.set_route("List", "Scheduled Operation", "Gantt");
			});
			frm.add_custom_button(__("Operations"), () => {
				frappe.route_options = { production_schedule: frm.doc.name };
				frappe.set_route("List", "Scheduled Operation", "List");
			});
		}
	},
});
