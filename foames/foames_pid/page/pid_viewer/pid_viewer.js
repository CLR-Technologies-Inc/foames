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

frappe.pages["pid-viewer"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("P&ID Viewer"),
		single_column: true,
	});
	const viewer = new PIDViewer(page);
	wrapper.pid_viewer = viewer;
	page.set_secondary_action(__("Refresh"), () => viewer.load());
	$(wrapper).on("remove", () => clearInterval(viewer.timer));
};

frappe.pages["pid-viewer"].on_page_show = function (wrapper) {
	const route = frappe.route_options || {};
	frappe.route_options = null;
	const viewer = wrapper.pid_viewer;
	if (route.drawing) {
		viewer.focus = route.tag || null;
		viewer.drawing_field.set_value(route.drawing);
	} else if (viewer.drawing) {
		viewer.load();
	}
};

class PIDViewer {
	constructor(page) {
		this.page = page;
		this.drawing = null;
		this.focus = null;
		this.drawing_field = page.add_field({
			fieldname: "drawing",
			label: __("Drawing"),
			fieldtype: "Link",
			options: "PID Drawing",
			change: () => {
				const value = this.drawing_field.get_value();
				if (value && value !== this.drawing) {
					this.drawing = value;
					this.load();
				}
			},
		});
		this.$body = $('<div class="foames-pid"></div>').appendTo(page.body);
		this.$body.append(`<style>
			.foames-pid .sheet-wrap { border: 1px solid var(--border-color); border-radius: 8px; overflow: auto; background: var(--bg-color); }
			.foames-pid .sheet-wrap svg { width: 100%; height: auto; min-width: 640px; display: block; }
			.foames-pid .focus .sym { stroke: #1565c0 !important; stroke-width: 1 !important; }
			.foames-pid .legend { margin: 8px 0; font-size: 12px; color: var(--text-muted); }
			.foames-pid .legend span { margin-right: 14px; }
			.foames-pid .legend i { display: inline-block; width: 10px; height: 10px; border: 1px solid #555; margin-right: 4px; }
			.foames-pid .empty { padding: 40px; text-align: center; color: var(--text-muted); }
		</style>`);
		this.$legend = $(`<div class="legend">
			<span><i style="background:#c8e6c9"></i>${__("Running")}</span>
			<span><i style="background:#fff3c4"></i>${__("Idle")}</span>
			<span><i style="background:#ffcdd2"></i>${__("Down")}</span>
			<span><i style="background:#bbdefb"></i>${__("Setup")}</span>
			<span><i style="background:#e0e0e0"></i>${__("Unknown")}</span>
			<span style="color:#c62828">${__("Red value: at a range limit")}</span>
			<span><em>${__("Grey value: stale")}</em></span>
		</div>`).appendTo(this.$body);
		this.$sheet = $('<div class="sheet-wrap"></div>').appendTo(this.$body);
		this.$sheet.html(`<div class="empty">${__("Choose a drawing")}</div>`);
		this.$sheet.on("click", "[data-tag]", (e) => {
			frappe.set_route("Form", "PID Component", $(e.currentTarget).attr("data-tag"));
		});
	}

	load() {
		if (!this.drawing) return;
		clearInterval(this.timer);
		frappe
			.call("foames.foames_pid.api.get_drawing_view", { drawing: this.drawing })
			.then((r) => {
				const view = r.message || {};
				this.page.set_title(
					`${__("P&ID")} ${frappe.utils.escape_html(view.drawing)}` +
						(view.revision
							? ` ${__("Rev")} ${frappe.utils.escape_html(view.revision)}`
							: "")
				);
				// The SVG is built server-side from escaped text only; it carries no script.
				this.$sheet.html(view.svg || "");
				if (!view.tags || !view.tags.length) {
					this.$sheet.append(
						`<div class="empty">${__(
							"This drawing has no components yet. Import a DEXPI file or add PID Components that name it."
						)}</div>`
					);
				}
				if (this.focus) {
					this.$sheet
						.find(`[data-tag="${CSS.escape(this.focus)}"]`)
						.addClass("focus")
						.each(function () {
							this.scrollIntoView({ block: "center", inline: "center" });
						});
				}
				this.timer = setInterval(() => this.load(), 30000);
			});
	}
}
