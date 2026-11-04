// Copyright (c) 2026, CLR Technologies Inc. and contributors
// For license information, please see license.txt

frappe.pages["floor-view"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Floor View"),
		single_column: true,
	});
	const view = new FloorView(page);
	page.set_secondary_action(__("Refresh"), () => view.refresh());
	if (frappe.model.can_create("Agent Suggestion")) {
		page.add_inner_button(__("Run suggestion rules"), () => {
			frappe.call("foames.foames_mes.api.run_suggestion_rules").then((r) => {
				frappe.show_alert({
					message: __("{0} new suggestions", [(r.message || []).length]),
					indicator: "blue",
				});
				view.refresh();
			});
		});
	}
	if (frappe.model.can_create("Andon Call")) {
		page.set_primary_action(__("Call for Help"), () => raise_andon_dialog(view));
	}
	view.refresh();
	view.timer = setInterval(() => view.refresh(), 30000);
	$(wrapper).on("remove", () => clearInterval(view.timer));
};

class FloorView {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="foames-floor"></div>').appendTo(page.body);
		this.$body.append(`<style>
			.foames-floor .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
			.foames-floor .tile { border-radius: 8px; padding: 12px; color: #fff; cursor: pointer; }
			.foames-floor .tile h4 { margin: 0 0 4px; color: #fff; }
			.foames-floor .tile small { opacity: .85; }
			.foames-floor .Running { background: #2e7d32; } .foames-floor .Idle { background: #f9a825; color: #222; }
			.foames-floor .Down { background: #c62828; } .foames-floor .Setup { background: #1565c0; } .foames-floor .Unknown { background: #616161; }
			.foames-floor .Idle h4, .foames-floor .Idle small { color: #222; }
			.foames-floor .metrics { display: flex; gap: 10px; margin-top: 6px; font-size: 12px; }
			.foames-floor h3 { margin: 18px 0 8px; }
			.foames-floor .sug { border-left: 4px solid #999; padding: 6px 10px; margin-bottom: 6px; background: var(--card-bg); }
			.foames-floor .sug.Critical { border-color: #c62828; } .foames-floor .sug.Warning { border-color: #f9a825; }
			.foames-floor .andon { margin-top: 6px; padding: 2px 8px; border-radius: 4px; background: #fff; color: #222; font-weight: 600; display: inline-block; }
			.foames-floor .andon.Open { animation: foames-andon 1s step-start infinite; }
			@keyframes foames-andon { 50% { background: #ffeb3b; } }
		</style>`);
	}

	refresh() {
		frappe
			.call("foames.foames_mes.api.get_floor_snapshot", { days: 1 })
			.then((r) => this.render(r.message));
	}

	render(snap) {
		const tiles = snap.machines
			.map((m) => {
				const counts = m.counts || {};
				const oee = m.oee_today;
				return `<div class="tile ${m.status}" data-machine="${frappe.utils.escape_html(
					m.name
				)}">
					<h4>${frappe.utils.escape_html(m.title || m.name)}</h4>
					<small>${__(m.status)}${m.last_seen ? " · " + frappe.datetime.prettyDate(m.last_seen) : ""}</small>
					${
						m.current_job
							? `<div>${__("Job")} ${frappe.utils.escape_html(
									m.current_job.external_id || m.current_job.reference
							  )}${
									m.current_job.label
										? " · " + frappe.utils.escape_html(m.current_job.label)
										: ""
							  }</div>`
							: ""
					}
					${m.shift ? `<div>${__("Shift")} ${frappe.utils.escape_html(m.shift.name)}</div>` : ""}
					${(m.andon || []).map((c) => andon_badge(c)).join("")}
					<div>${
						m.minutes_since_count == null
							? __("No counts today")
							: __("Last count {0} min ago", [Math.round(m.minutes_since_count)])
					}</div>
					<div class="metrics">
						<span>${__("Good")} ${counts.good || 0}</span><span>${__("Scrap")} ${counts.scrap || 0}</span>
						${oee ? `<span>OEE ${Math.round(oee.oee || 0)}%</span>` : ""}
					</div>
				</div>`;
			})
			.join("");
		const suggestions = snap.open_suggestions
			.map(
				(s) => `<div class="sug ${s.severity}">
					<a href="/app/agent-suggestion/${encodeURIComponent(s.name)}"><b>${frappe.utils.escape_html(
					s.title
				)}</b></a>
					<small> · ${__(s.category)} · ${frappe.utils.escape_html(s.agent || "")}</small>
				</div>`
			)
			.join("");
		this.$body.find(".content").remove();
		this.$body.append(`<div class="content">
			<div class="grid">${
				tiles || `<p>${__("No machines yet. Create a Machine to see it here.")}</p>`
			}</div>
			<h3>${__("Open suggestions")} (${snap.open_suggestions.length})</h3>
			${suggestions || `<p class="text-muted">${__("None")}</p>`}
			<p class="text-muted small">${__("As of")} ${frappe.datetime.str_to_user(snap.as_of)}</p>
		</div>`);
		this.$body
			.find(".tile")
			.on("click", (e) =>
				frappe.set_route("Form", "Machine", $(e.currentTarget).data("machine"))
			);
	}
}

function andon_badge(call) {
	const minutes = Math.round(call.minutes_open || 0);
	return `<div class="andon ${call.status}" title="${frappe.utils.escape_html(call.note || "")}">
		${__("Andon")}: ${frappe.utils.escape_html(call.call_type)} · ${__(call.status)} · ${minutes} min
	</div>`;
}

function raise_andon_dialog(view) {
	const dialog = new frappe.ui.Dialog({
		title: __("Call for Help"),
		fields: [
			{
				fieldname: "machine",
				label: __("Machine"),
				fieldtype: "Link",
				options: "Machine",
				reqd: 1,
			},
			{
				fieldname: "call_type",
				label: __("Call Type"),
				fieldtype: "Link",
				options: "Andon Call Type",
				reqd: 1,
				get_query: () => ({ filters: { disabled: 0 } }),
			},
			{ fieldname: "note", label: __("Note"), fieldtype: "Small Text" },
		],
		primary_action_label: __("Raise"),
		primary_action(values) {
			frappe
				.call({
					method: "foames.foames_mes.doctype.andon_call.andon_call.raise_andon",
					args: values,
				})
				.then((r) => {
					dialog.hide();
					frappe.show_alert({
						message: __("Andon call {0} raised", [r.message.name]),
						indicator: "orange",
					});
					view.refresh();
				});
		},
	});
	dialog.show();
}
