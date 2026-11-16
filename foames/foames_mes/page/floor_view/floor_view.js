// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

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
	// The data layer over the floor: each tile shows the signals bound to the machine (and to the
	// instruments on it) and their freshness, from the snapshot's topology section.
	if (frappe.boot.user.can_read.includes("Topology Asset")) {
		page.add_inner_button(__("Data layer"), () => {
			view.data_layer = !view.data_layer;
			view.render(view.snap);
		});
		page.add_inner_button(__("Topology View"), () => frappe.set_route("topology-view"));
	}
	if (frappe.model.can_create("Work Instruction Run")) {
		page.add_inner_button(__("Work Instructions"), () => start_work_instruction_dialog(view));
	}
	wrapper.floor_view = view;
	view.refresh();
	view.timer = setInterval(() => view.refresh(), 30000);
	$(wrapper).on("remove", () => clearInterval(view.timer));
};

frappe.pages["floor-view"].on_page_show = function (wrapper) {
	// The Work Instruction Run form opens its run here.
	const run = frappe.route_options && frappe.route_options.work_instruction_run;
	if (run && wrapper.floor_view) {
		frappe.route_options = null;
		new WorkInstructionRunner(run, wrapper.floor_view).open();
	}
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
			.foames-floor .data { margin-top: 6px; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,.9); color: #222; font-size: 12px; display: inline-block; }
			.foames-floor .data i { display: inline-block; width: 8px; height: 8px; border-radius: 4px; margin-right: 4px; }
			.foames-floor .andon.Open { animation: foames-andon 1s step-start infinite; }
			.foames-floor .wi-run { margin-top: 6px; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,.9); color: #222; display: inline-block; cursor: pointer; }
			.foames-floor .wi-run.On.Hold { background: #ffcdd2; font-weight: 600; }
			@keyframes foames-andon { 50% { background: #ffeb3b; } }
		</style>`);
	}

	refresh() {
		frappe
			.call("foames.foames_mes.api.get_floor_snapshot", { days: 1 })
			.then((r) => this.render(r.message));
	}

	render(snap) {
		if (!snap) return;
		this.snap = snap;
		const topology = snap.topology || {};
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
					${(m.work_instruction_runs || []).map((r) => work_instruction_badge(r)).join("")}
					<div>${
						m.minutes_since_count == null
							? __("No counts today")
							: __("Last count {0} min ago", [Math.round(m.minutes_since_count)])
					}</div>
					${this.data_layer ? data_badge(topology[m.name]) : ""}
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
		this.$body.find(".wi-run").on("click", (e) => {
			e.stopPropagation();
			new WorkInstructionRunner($(e.currentTarget).data("run"), this).open();
		});
		this.$body
			.find(".tile")
			.on("click", (e) =>
				frappe.set_route("Form", "Machine", $(e.currentTarget).data("machine"))
			);
	}
}

const DATA_HEALTH = { fresh: "#2e7d32", stale: "#f9a825", "no data": "#9e9e9e", fault: "#c62828" };

function data_badge(entry) {
	if (!entry || !entry.signals) {
		return `<div class="data"><i style="background:#9e9e9e"></i>${__(
			"No signals bound"
		)}</div>`;
	}
	const parts = [__("{0} signals", [entry.signals])];
	if (entry.stale) parts.push(__("{0} stale", [entry.stale]));
	if (entry.no_data) parts.push(__("{0} no data", [entry.no_data]));
	const title = (entry.detail || [])
		.map(
			(s) =>
				`${s.tag || s.title}: ${s.value == null ? "" : s.value + " " + (s.unit || "")} (${
					s.health
				})`
		)
		.join("\n");
	return `<div class="data" title="${frappe.utils.escape_html(title)}"><i style="background:${
		DATA_HEALTH[entry.health] || "#9e9e9e"
	}"></i>${parts.join(" · ")}${
		entry.feeds && entry.feeds.length
			? " → " + frappe.utils.escape_html(entry.feeds.join(", "))
			: ""
	}</div>`;
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

// Work instructions
// -----------------

const WIR_METHODS = "foames.foames_mes.doctype.work_instruction_run.work_instruction_run";

function work_instruction_badge(run) {
	const step = run.current_step
		? __("step {0} of {1}", [run.current_step, run.steps_total])
		: __("ready to complete");
	return `<div class="wi-run ${frappe.utils.escape_html(
		run.status
	)}" data-run="${frappe.utils.escape_html(run.name)}" title="${frappe.utils.escape_html(
		run.current_title || ""
	)}">
		${__("WI")}: ${frappe.utils.escape_html(run.title || run.work_instruction)} · ${step}${
		run.status === "On Hold" ? " · " + __("On Hold") : ""
	}
	</div>`;
}

function start_work_instruction_dialog(view) {
	const dialog = new frappe.ui.Dialog({
		title: __("Start a Work Instruction"),
		fields: [
			{
				fieldname: "machine",
				label: __("Machine"),
				fieldtype: "Link",
				options: "Machine",
				onchange: () => load_instructions(),
			},
			{ fieldname: "instructions", fieldtype: "HTML" },
		],
	});
	const load_instructions = () => {
		const machine = dialog.get_value("machine");
		frappe
			.call({
				method: "foames.foames_mes.doctype.work_instruction.work_instruction.list_instructions_for_machine",
				args: { machine },
			})
			.then((r) => {
				const rows = r.message || [];
				const $area = dialog.fields_dict.instructions.$wrapper;
				if (!rows.length) {
					$area.html(
						`<p class="text-muted">${__(
							"No released work instructions apply here."
						)}</p>`
					);
					return;
				}
				$area.html(
					rows
						.map(
							(
								wi
							) => `<div class="flex justify-between align-center" style="padding:6px 0;border-bottom:1px solid var(--border-color)">
							<div><b>${frappe.utils.escape_html(wi.title)}</b>
								<div class="text-muted small">${frappe.utils.escape_html(wi.instruction_code)} ${__("rev")} ${
								wi.revision
							}${
								wi.operation ? " · " + frappe.utils.escape_html(wi.operation) : ""
							}${
								wi.estimated_minutes
									? " · " +
									  __("about {0} min", [Math.round(wi.estimated_minutes)])
									: ""
							} · ${__(wi.scope)}</div></div>
							<button class="btn btn-sm btn-primary" data-wi="${frappe.utils.escape_html(wi.name)}">${__(
								"Start"
							)}</button></div>`
						)
						.join("")
				);
				$area.find("button[data-wi]").on("click", (e) => {
					frappe
						.call({
							method: `${WIR_METHODS}.start_run`,
							args: { work_instruction: $(e.currentTarget).data("wi"), machine },
						})
						.then((res) => {
							dialog.hide();
							view.refresh();
							new WorkInstructionRunner(res.message.name, view, res.message).open();
						});
				});
			});
	};
	dialog.show();
	load_instructions();
}

function step_mark(step, current) {
	if (step.result === "Fail") return "✗";
	if (step.result === "Skipped") return "–";
	if (step.result) return "✓";
	return step.step_no === current ? "▶" : "○";
}

class WorkInstructionRunner {
	constructor(name, view, run) {
		this.name = name;
		this.view = view;
		this.run = run;
	}

	open() {
		this.dialog = new frappe.ui.Dialog({
			title: __("Work Instruction"),
			size: "large",
			fields: [{ fieldname: "body", fieldtype: "HTML" }],
		});
		this.dialog.show();
		this.dialog.$wrapper.on("hidden.bs.modal", () => this.view && this.view.refresh());
		if (this.run) {
			this.render(this.run);
		} else {
			this.reload();
		}
	}

	reload() {
		frappe
			.call({ method: `${WIR_METHODS}.get_run`, args: { name: this.name } })
			.then((r) => this.render(r.message));
	}

	call(method, args) {
		return frappe
			.call({ method: `${WIR_METHODS}.${method}`, args: { name: this.name, ...args } })
			.then((r) => this.render(r.message));
	}

	render(run) {
		this.run = run;
		const esc = frappe.utils.escape_html;
		this.dialog.set_title(`${run.title} · ${run.name}`);
		const step = run.steps.find((s) => s.step_no === run.current_step);
		const list = run.steps
			.map((s) => {
				const mark = step_mark(s, run.current_step);
				const signed = s.sign_off_role
					? s.signed_off_by
						? ` · ${__("signed off by {0}", [esc(s.signed_off_by)])}`
						: ` · ${__("needs sign-off by {0}", [esc(s.sign_off_role)])}`
					: "";
				return `<div style="padding:2px 0"><b>${mark}</b> ${s.step_no}. ${esc(s.title)}${
					s.value_text
						? ` · <b>${esc(s.value_text)}</b>${s.unit ? " " + esc(s.unit) : ""}`
						: ""
				}${s.result ? ` · ${__(s.result)}` : ""}${signed}</div>`;
			})
			.join("");
		let header = `<div class="text-muted small">${__("Revision")} ${run.revision}${
			run.machine ? " · " + esc(run.machine) : ""
		} · ${__(run.status)} · ${run.progress.done}/${run.progress.total}</div>`;
		if (run.safety_notes && !run.steps.some((s) => s.result)) {
			header += `<div class="alert alert-warning" style="margin-top:8px"><b>${__(
				"Safety"
			)}</b>: ${esc(run.safety_notes)}</div>`;
		}
		if (run.status === "On Hold") {
			header += `<div class="alert alert-danger" style="margin-top:8px">${__(
				"On hold"
			)}: ${esc(run.hold_reason || "")}</div>`;
		}
		this.dialog.fields_dict.body.$wrapper.html(`${header}
			<div class="row" style="margin-top:8px">
				<div class="col-md-8 wi-step"></div>
				<div class="col-md-4 small" style="border-left:1px solid var(--border-color)">${list}</div>
			</div>
			<div class="wi-actions" style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap"></div>`);
		const $step = this.dialog.$wrapper.find(".wi-step");
		const $actions = this.dialog.$wrapper.find(".wi-actions");
		if (["Completed", "Aborted"].includes(run.status)) {
			$step.html(`<p>${__("This run is {0}.", [__(run.status)])}</p>`);
			return;
		}
		if (step) {
			this.render_step(step, $step, $actions);
		} else {
			$step.html(`<p>${__("Every step is recorded.")}</p>`);
			this.button($actions, __("Complete"), "btn-primary", () => this.call("complete_run"));
		}
		if (run.status === "On Hold") {
			this.button($actions, __("Release Hold"), "btn-default", () =>
				frappe.prompt(
					{
						fieldname: "disposition",
						label: __("Disposition"),
						fieldtype: "Small Text",
						reqd: 1,
					},
					(v) => this.call("release_hold", { disposition: v.disposition }),
					__("What was decided about the failed step?")
				)
			);
		}
		this.button($actions, __("Abort"), "btn-default", () =>
			frappe.prompt(
				{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
				(v) => this.call("abort_run", { reason: v.reason }),
				__("Abort the run")
			)
		);
	}

	render_step(step, $step, $actions) {
		const esc = frappe.utils.escape_html;
		const media = [
			step.image ? `<img src="${esc(step.image)}" style="max-width:100%;margin:8px 0">` : "",
			step.attachment
				? `<div><a href="${esc(step.attachment)}" target="_blank" rel="noopener">${__(
						"Open attachment"
				  )}</a></div>`
				: "",
			step.video_url
				? `<div><a href="${esc(step.video_url)}" target="_blank" rel="noopener">${__(
						"Watch video"
				  )}</a></div>`
				: "",
		].join("");
		const limits = [
			step.has_lower_limit ? `≥ ${step.lower_limit}` : "",
			step.has_upper_limit ? `≤ ${step.upper_limit}` : "",
		]
			.filter(Boolean)
			.join(" ");
		$step.html(`<h4>${__("Step {0}", [step.step_no])}: ${esc(step.title)}</h4>
			<div>${frappe.dom.remove_script_and_style(step.instruction || "")}</div>${media}
			${
				step.capture === "Number"
					? `<div class="text-muted small">${limits ? __("Limits") + " " + limits : ""}${
							step.unit ? " " + esc(step.unit) : ""
					  }${
							step.target_value ? " · " + __("target {0}", [step.target_value]) : ""
					  }</div>`
					: ""
			}
			<div class="wi-input" style="margin-top:8px"></div>`);
		if (step.result) {
			// Recorded, waiting for its verification.
			$step
				.find(".wi-input")
				.html(
					`<div class="alert alert-info">${__(
						"Waiting for a sign-off by {0}. Ask someone else with that role to sign it off.",
						[esc(step.sign_off_role)]
					)}</div>`
				);
			if (
				frappe.user.has_role(step.sign_off_role) &&
				step.completed_by !== frappe.session.user
			) {
				this.button($actions, __("Sign Off Step {0}", [step.step_no]), "btn-primary", () =>
					this.call("sign_off_step", { step_no: step.step_no })
				);
			}
			return;
		}
		if (this.run.status !== "In Progress") return;
		const fields = [];
		if (step.capture === "Number") {
			fields.push({ fieldname: "value", label: __("Value"), fieldtype: "Float", reqd: 1 });
		} else if (step.capture === "Text") {
			fields.push({
				fieldname: "value",
				label: __("What you found"),
				fieldtype: "Data",
				reqd: 1,
			});
		} else if (step.capture === "Choice") {
			fields.push({
				fieldname: "value",
				label: __("Answer"),
				fieldtype: "Select",
				options: [
					"",
					...(step.choices || "")
						.split("\n")
						.map((c) => c.trim())
						.filter(Boolean),
				],
				reqd: 1,
			});
		}
		fields.push({ fieldname: "note", label: __("Note"), fieldtype: "Small Text" });
		const form = new frappe.ui.FieldGroup({ fields, body: $step.find(".wi-input") });
		form.make();
		const record = (value) => {
			const values = form.get_values(value !== undefined);
			if (!values) return;
			this.call("record_step", {
				step_no: step.step_no,
				value: value !== undefined ? value : values.value,
				note: values.note,
			});
		};
		if (step.capture === "Pass/Fail") {
			this.button($actions, __("Pass"), "btn-success", () => record("Pass"));
			this.button($actions, __("Fail"), "btn-danger", () => record("Fail"));
		} else {
			this.button(
				$actions,
				step.capture === "Confirm" ? __("Done") : __("Record"),
				"btn-primary",
				() => record()
			);
		}
		if (step.optional) {
			this.button($actions, __("Skip"), "btn-default", () =>
				this.call("record_step", { step_no: step.step_no, skip: 1 })
			);
		}
	}

	button($area, label, cls, action) {
		$(`<button class="btn btn-sm ${cls}">${label}</button>`)
			.appendTo($area)
			.on("click", action);
	}
}
