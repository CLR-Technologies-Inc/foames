// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

// The live topology: the physical layer along the bottom, the data layer drawn over it, and the
// bindings between them. Everything is generated from the graph API; nothing here is drawn by hand.
// Node colour is the physical status, the badge is the data health. Click a node to trace its
// lineage (downstream from equipment, upstream from data), shift-click to open its record.

frappe.pages["topology-view"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Topology View"),
		single_column: true,
	});
	const view = new TopologyView(page);
	page.set_secondary_action(__("Refresh"), () => view.refresh());
	page.add_inner_button(__("Copy Mermaid"), () => view.copy_mermaid(), __("Export"));
	page.add_inner_button(
		__("Grafana Node Graph JSON"),
		() => window.open(view.url("foames.foames_topology.api.grafana"), "_blank"),
		__("Export")
	);
	if (frappe.user.has_role(["System Manager", "FoaMES Engineer"])) {
		page.add_inner_button(__("Sync now"), () =>
			frappe
				.call({ method: "foames.foames_topology.api.sync_now", freeze: true })
				.then(() => view.refresh())
		);
	}
	view.refresh();
	view.timer = setInterval(() => view.refresh(), 30000);
	$(wrapper).on("remove", () => clearInterval(view.timer));
};

const HEALTH = { fresh: "#2e7d32", stale: "#f9a825", "no data": "#9e9e9e", fault: "#c62828" };
const STATUS = {
	Running: "#2e7d32",
	OK: "#2e7d32",
	Idle: "#f9a825",
	Setup: "#1565c0",
	Down: "#c62828",
	Maintenance: "#6a1b9a",
	Stale: "#9e9e9e",
	Retired: "#424242",
	Unknown: "#616161",
};
const EDGE = { Physical: "#8d6e63", Data: "#1e88e5", Binding: "#ab47bc" };

class TopologyView {
	constructor(page) {
		this.page = page;
		this.show = { Physical: true, Data: true, Binding: true };
		this.trace = null;
		this.tenant = page.add_field({
			fieldname: "tenant",
			label: __("Tenant"),
			fieldtype: "Link",
			options: "Topology Tenant",
			change: () => this.refresh(),
		});
		this.provider = page.add_field({
			fieldname: "provider",
			label: __("Provider"),
			fieldtype: "Data",
			change: () => this.refresh(),
		});
		for (const layer of ["Physical", "Data", "Binding"]) {
			page.add_field({
				fieldname: "show_" + layer.toLowerCase(),
				label: layer === "Binding" ? __("Bindings") : __("{0} layer", [__(layer)]),
				fieldtype: "Check",
				default: 1,
				change: (e) => {
					this.show[layer] = !!$(e.target).prop("checked");
					this.draw();
				},
			});
		}
		this.$body = $('<div class="foames-topology"></div>').appendTo(page.body);
		this.$body.append(`<style>
			.foames-topology svg { width: 100%; border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg); }
			.foames-topology .node rect { rx: 8; stroke: rgba(0,0,0,.25); }
			.foames-topology .node text { fill: #fff; font-size: 11px; pointer-events: none; }
			.foames-topology .node.dim, .foames-topology .edge.dim { opacity: .15; }
			.foames-topology .node { cursor: pointer; }
			.foames-topology .band { font-size: 12px; fill: var(--text-muted); }
			.foames-topology .legend span { display: inline-block; margin-right: 12px; font-size: 12px; }
			.foames-topology .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 5px; margin-right: 4px; vertical-align: middle; }
			.foames-topology .finding { border-left: 4px solid #999; padding: 4px 10px; margin-bottom: 4px; background: var(--card-bg); font-size: 12px; }
			.foames-topology .finding.Critical { border-color: #c62828; } .foames-topology .finding.Warning { border-color: #f9a825; }
		</style>`);
	}

	args() {
		const args = {};
		const tenant = this.tenant.get_value();
		const provider = this.provider.get_value();
		if (tenant) args.tenant = tenant;
		if (provider) args.provider = provider;
		return args;
	}

	url(method) {
		const query = new URLSearchParams(this.args()).toString();
		return `/api/method/${method}${query ? "?" + query : ""}`;
	}

	refresh() {
		frappe.call("foames.foames_topology.api.get_graph", this.args()).then((r) => {
			this.data = r.message;
			this.draw();
		});
	}

	copy_mermaid() {
		frappe.call("foames.foames_topology.api.get_mermaid", this.args()).then((r) => {
			frappe.utils.copy_to_clipboard(r.message);
		});
	}

	draw() {
		const data = this.data;
		if (!data) return;
		const esc = frappe.utils.escape_html;
		const pos = data.layout || {};
		const nodes = data.nodes.filter((n) => this.show[n.layer] && pos[n.id]);
		const shown = new Set(nodes.map((n) => n.id));
		const edges = data.edges.filter(
			(e) =>
				this.show[e.layer] &&
				shown.has(e.source) &&
				shown.has(e.target) &&
				e.type !== "Contains"
		);
		const W = 150,
			H = 44;
		const xs = nodes.map((n) => pos[n.id].x),
			ys = nodes.map((n) => pos[n.id].y);
		const minX = Math.min(0, ...xs) - 20,
			maxX = Math.max(400, ...xs) + W + 20;
		const maxY = Math.max(200, ...ys) + H + 30;
		const lit = this.trace ? new Set(this.trace.nodes) : null;
		const litEdges = this.trace ? new Set(this.trace.edges) : null;
		const center = (id) => [pos[id].x + W / 2, pos[id].y + H / 2];

		const physicalTop = Math.min(
			...data.nodes
				.filter((n) => n.layer === "Physical" && pos[n.id])
				.map((n) => pos[n.id].y),
			maxY
		);
		let svg = `<svg viewBox="${minX} 0 ${maxX - minX} ${maxY}" style="height:${Math.min(
			900,
			Math.max(320, maxY)
		)}px">
			<defs><marker id="foames-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
			<path d="M 0 0 L 10 5 L 0 10 z" fill="#888"/></marker></defs>`;
		if (this.show.Data)
			svg += `<text class="band" x="${minX + 8}" y="16">${__("Data layer")}</text>`;
		if (this.show.Physical && physicalTop < maxY)
			svg += `<line x1="${minX}" x2="${maxX}" y1="${physicalTop - 20}" y2="${
				physicalTop - 20
			}" stroke="var(--border-color)" stroke-dasharray="6 4"/>
				<text class="band" x="${minX + 8}" y="${physicalTop - 26}">${__("Physical layer")}</text>`;

		for (const e of edges) {
			const [x1, y1] = center(e.source),
				[x2, y2] = center(e.target);
			const dim = litEdges && !litEdges.has(e.id) ? "dim" : "";
			const dash = e.layer === "Binding" ? 'stroke-dasharray="4 3"' : "";
			const arrow = e.layer === "Physical" ? "" : 'marker-end="url(#foames-arrow)"';
			svg += `<g class="edge ${dim}"><title>${esc(e.type)}${
				e.tag ? " " + esc(e.tag) : ""
			}</title>
				<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${
				EDGE[e.layer]
			}" stroke-width="1.5" ${dash} ${arrow}/></g>`;
		}
		for (const n of nodes) {
			const p = pos[n.id];
			const dim = lit && !lit.has(n.id) ? "dim" : "";
			const fill =
				n.layer === "Data" && (n.health === "stale" || n.health === "fault")
					? HEALTH[n.health]
					: STATUS[n.status] || STATUS.Unknown;
			const title = (n.title || n.id).slice(0, 22);
			const badge = n.health
				? `<circle cx="${p.x + W - 8}" cy="${p.y + 8}" r="5" fill="${
						HEALTH[n.health]
				  }" stroke="#fff"/>`
				: "";
			svg += `<g class="node ${dim}" data-id="${esc(n.id)}">
				<title>${esc(n.id)} · ${esc(n.kind)} · ${esc(n.status)}${n.health ? " · " + esc(n.health) : ""}${
				n.tenant ? " · " + esc(n.tenant) : ""
			}${n.provider ? " · " + esc(n.provider) : ""}</title>
				<rect x="${p.x}" y="${p.y}" width="${W}" height="${H}" fill="${fill}"/>
				${badge}
				<text x="${p.x + 8}" y="${p.y + 18}" font-weight="600">${esc(title)}</text>
				<text x="${p.x + 8}" y="${p.y + 34}" opacity=".85">${esc(__(n.kind))}${
				n.signal_count ? " · " + n.signal_count + " " + __("signals") : ""
			}</text></g>`;
		}
		svg += "</svg>";

		const legend = Object.entries(HEALTH)
			.map(([k, c]) => `<span><i style="background:${c}"></i>${__(k)}</span>`)
			.join("");
		const edgeLegend = Object.entries(EDGE)
			.map(([k, c]) => `<span><i style="background:${c}"></i>${__(k)}</span>`)
			.join("");
		const findings = (data.findings || [])
			.slice(0, 50)
			.map(
				(f) =>
					`<div class="finding ${f.severity}"><b>${esc(f.rule)}</b> · ${esc(
						f.message
					)}</div>`
			)
			.join("");
		this.$body.find(".content").remove();
		this.$body.append(`<div class="content">
			<p class="legend">${__("Data health")}: ${legend} &nbsp; ${__("Links")}: ${edgeLegend}</p>
			${
				this.trace
					? `<p>${__("Tracing {0} {1}", [
							esc(this.trace.direction),
							esc(this.trace.start),
					  ])} · <a class="clear-trace">${__("Clear")}</a></p>`
					: ""
			}
			${
				nodes.length
					? svg
					: `<p>${__(
							"Nothing in the graph yet. Create Machines, or press Sync now."
					  )}</p>`
			}
			<h4 style="margin-top:16px">${__("Findings")} (${(data.findings || []).length})</h4>
			${findings || `<p class="text-muted">${__("None")}</p>`}
			<p class="text-muted small">${__("As of")} ${frappe.datetime.str_to_user(data.as_of)}${
			data.last_sync_at
				? " · " + __("Last sync") + " " + frappe.datetime.prettyDate(data.last_sync_at)
				: ""
		}</p>
		</div>`);
		this.$body.find(".clear-trace").on("click", () => {
			this.trace = null;
			this.draw();
		});
		this.$body.find(".node").on("click", (ev) => {
			const id = $(ev.currentTarget).data("id");
			const node = data.nodes.find((n) => n.id === id);
			if (ev.shiftKey && node) {
				if (node.source_doctype && node.source_name)
					frappe.set_route("Form", node.source_doctype, node.source_name);
				else frappe.set_route("Form", "Topology Asset", id);
				return;
			}
			const direction = node && node.layer === "Physical" ? "downstream" : "upstream";
			frappe
				.call("foames.foames_topology.api.trace", { asset: id, direction, ...this.args() })
				.then((r) => {
					this.trace = r.message;
					this.draw();
				});
		});
	}
}
