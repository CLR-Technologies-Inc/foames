# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The topology graph: build, filter, check, trace, lay out and export. No Frappe needed.

Input is three lists of plain dicts with the fields of Topology Asset, Topology Link and Signal
Binding. The api module reads them from the site (through the user's permissions) and passes them
here, the tests build them by hand, and any other app can do the same.

The graph is one structure with two layers that share node ids (see model.py). Every view and
export is generated from it, so nobody draws or edits a diagram by hand:

* graph_dict() for the Topology View page and agents,
* to_mermaid() for docs and pull requests,
* to_grafana() for Grafana's Node Graph panel (through the Infinity data source or any JSON one),
* overlay() for a view that already draws the physical layer, such as Floor View or a P&ID,
  and wants the data-layer health of each of its nodes.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime

from foames.foames_topology import model


def _parse_time(value):
	if value in (None, ""):
		return None
	if isinstance(value, datetime):
		return value
	text = str(value).replace("T", " ").rstrip("Z")
	for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
		try:
			return datetime.strptime(text, fmt)
		except ValueError:
			continue
	return None


def data_health(node: dict, now: datetime, stale_after_seconds: int) -> str:
	"""fresh, stale, no data or fault, from a node's last-seen time and status. Only streaming
	kinds (model.STREAMING_KINDS) go stale.

	A physical node's health is the worst of the signals bound to it (see build_graph)."""
	if node.get("status") == "Down" and node.get("layer") == model.DATA:
		return model.FAULT
	seen = _parse_time(node.get("last_seen"))
	if seen is None:
		return model.NO_DATA
	if node.get("kind") not in model.STREAMING_KINDS:
		return model.FRESH
	limit = node.get("stale_after_seconds") or stale_after_seconds
	if limit and (now - seen).total_seconds() > limit:
		return model.STALE
	return model.FRESH


_HEALTH_ORDER = {model.FRESH: 0, model.NO_DATA: 1, model.STALE: 2, model.FAULT: 3}


def worst_health(healths):
	healths = list(healths)
	if not healths:
		return None
	return max(healths, key=lambda h: _HEALTH_ORDER[h])


class Graph:
	"""nodes: id -> node dict; edges: list of edge dicts with id, source, target, type, layer."""

	def __init__(self, nodes: dict, edges: list, now: datetime, stale_after_seconds: int):
		self.nodes = nodes
		self.edges = edges
		self.now = now
		self.stale_after_seconds = stale_after_seconds

	def out_edges(self, node_id, types=None):
		return [e for e in self.edges if e["source"] == node_id and (types is None or e["type"] in types)]

	def in_edges(self, node_id, types=None):
		return [e for e in self.edges if e["target"] == node_id and (types is None or e["type"] in types)]


def build_graph(
	assets: list[dict],
	links: list[dict],
	bindings: list[dict],
	*,
	now: datetime,
	stale_after_seconds: int = 900,
	include_disabled: bool = False,
) -> Graph:
	"""The graph from the three record lists.

	Disabled assets are left out unless include_disabled, so a retired machine drops off the
	views; the checks in findings() still see bindings that point at it, because those are
	kept as dangling edges (target missing) rather than silently dropped."""
	nodes = {}
	for a in assets:
		if a.get("disabled") and not include_disabled:
			continue
		node_id = a["asset_id"]
		nodes[node_id] = {
			"id": node_id,
			"title": a.get("title") or node_id,
			"layer": a.get("layer") or model.kind_layer(a.get("kind")) or model.DATA,
			"kind": a.get("kind") or "Other",
			"parent": a.get("parent_asset") or None,
			"status": a.get("status") or "Unknown",
			"last_seen": a.get("last_seen"),
			"tenant": a.get("tenant") or None,
			"provider": a.get("provider") or None,
			"source_doctype": a.get("source_doctype") or None,
			"source_name": a.get("source_name") or None,
			"disabled": bool(a.get("disabled")),
		}
	edges = []
	# Containment is stored on the asset (parent_asset) and drawn as a Contains edge.
	for node in nodes.values():
		if node["parent"]:
			edges.append(
				{
					"id": f"contains:{node['parent']}>{node['id']}",
					"source": node["parent"],
					"target": node["id"],
					"type": "Contains",
					"layer": model.PHYSICAL,
					"tenant": node["tenant"],
					"provider": node["provider"],
				}
			)
	for link in links:
		if link.get("disabled") and not include_disabled:
			continue
		link_type = link.get("link_type") or "Data Flow"
		edges.append(
			{
				"id": link.get("link_key") or f"{link['from_asset']}|{link_type}|{link['to_asset']}",
				"source": link["from_asset"],
				"target": link["to_asset"],
				"type": link_type,
				"layer": model.LINK_TYPES.get(link_type, model.DATA),
				"tenant": link.get("tenant") or None,
				"provider": link.get("provider") or None,
				"status": link.get("status") or None,
			}
		)
	for b in bindings:
		if b.get("disabled") and not include_disabled:
			continue
		direction = b.get("direction") or "Read"
		edges.append(
			{
				"id": b.get("binding_key") or f"{b['signal']}|{direction}|{b['physical_asset']}",
				"source": b["signal"],
				"target": b["physical_asset"],
				"type": model.DIRECTIONS.get(direction, "Measured At"),
				"layer": model.BINDING,
				"direction": direction,
				"unit": b.get("unit") or None,
				"tag": b.get("tag") or None,
				"tenant": b.get("tenant") or None,
				"provider": b.get("provider") or None,
			}
		)
		# A binding's own reading time and threshold, when the collector keeps them on the binding
		# rather than on the signal asset.
		signal = nodes.get(b["signal"])
		if signal is not None:
			if b.get("last_value_at"):
				seen = _parse_time(b["last_value_at"])
				current = _parse_time(signal.get("last_seen"))
				if seen and (current is None or seen > current):
					signal["last_seen"] = b["last_value_at"]
			if b.get("last_value") is not None and "last_value" not in signal:
				signal["last_value"] = b["last_value"]
				signal["unit"] = b.get("unit")
			if b.get("stale_after_seconds"):
				signal["stale_after_seconds"] = b["stale_after_seconds"]

	graph = Graph(nodes, edges, now, stale_after_seconds)
	for node in nodes.values():
		if node["layer"] == model.DATA:
			node["health"] = data_health(node, now, stale_after_seconds)
	# A physical node's data health is the worst of the signals bound to it; one with none is None.
	for node in nodes.values():
		if node["layer"] != model.PHYSICAL:
			continue
		bound = [
			nodes[e["source"]]["health"]
			for e in graph.in_edges(node["id"], types=tuple(model.DIRECTIONS.values()))
			if e["source"] in nodes
		]
		node["health"] = worst_health(bound)
		node["signal_count"] = len(bound)
	return graph


def filter_graph(graph: Graph, *, tenants=None, layers=None, providers=None) -> Graph:
	"""The subgraph a view shows.

	tenants: an iterable of tenant names; None means every tenant the caller could read (the
	combined owner view, which is read-only like every other view). A node with no tenant is
	shared infrastructure and stays in every tenant's view.
	layers: Physical and/or Data. Binding edges are kept when both of their ends are kept.
	providers: only nodes a given plugin or adapter provides."""
	tenants = set(tenants) if tenants else None
	layers = set(layers) if layers else None
	providers = set(providers) if providers else None

	def keep(node):
		if tenants is not None and node["tenant"] is not None and node["tenant"] not in tenants:
			return False
		if layers is not None and node["layer"] not in layers:
			return False
		if providers is not None and node["provider"] not in providers:
			return False
		return True

	nodes = {k: v for k, v in graph.nodes.items() if keep(v)}
	edges = [
		e
		for e in graph.edges
		if e["source"] in nodes
		and e["target"] in nodes
		and (tenants is None or e.get("tenant") is None or e["tenant"] in tenants)
	]
	return Graph(nodes, edges, graph.now, graph.stale_after_seconds)


def findings(graph: Graph) -> list[dict]:
	"""What the graph says is wrong or missing. Each finding: rule, severity, asset, message.

	* unbound: a machine, instrument or valve with no signal bound to it (a gap in the data layer);
	* dangling: a link or binding whose other end is not in the register any more (drift);
	* stale: a signal whose last reading is older than its threshold;
	* cross-tenant: a link or binding between two different tenants (isolation breach);
	* write-binding: a signal bound to act on equipment (shown, never executed by FoaMES)."""
	out = []
	nodes = graph.nodes
	bound_types = tuple(model.DIRECTIONS.values())
	for node in nodes.values():
		if node["layer"] == model.PHYSICAL and node["kind"] in model.EXPECTS_SIGNALS:
			if not node.get("signal_count"):
				out.append(
					{
						"rule": "unbound",
						"severity": "Info",
						"asset": node["id"],
						"message": f"{node['title']} has no signal bound to it",
					}
				)
		if node["layer"] == model.DATA and node["kind"] == "Signal" and node.get("health") == model.STALE:
			out.append(
				{
					"rule": "stale",
					"severity": "Warning",
					"asset": node["id"],
					"message": f"{node['title']} has not reported since {node.get('last_seen')}",
				}
			)
	for e in graph.edges:
		missing = [end for end in (e["source"], e["target"]) if end not in nodes]
		if missing:
			out.append(
				{
					"rule": "dangling",
					"severity": "Warning",
					"asset": e["source"] if e["source"] in nodes else e["target"],
					"edge": e["id"],
					"message": f"{e['type']} {e['source']} → {e['target']} points at "
					+ ", ".join(missing)
					+ ", which is not in the register (or is retired)",
				}
			)
			continue
		a, b = nodes[e["source"]]["tenant"], nodes[e["target"]]["tenant"]
		if a and b and a != b:
			out.append(
				{
					"rule": "cross-tenant",
					"severity": "Critical",
					"asset": e["source"],
					"edge": e["id"],
					"message": f"{e['type']} joins tenant {a} to tenant {b}",
				}
			)
		if e["type"] in bound_types and e.get("direction") == "Write":
			out.append(
				{
					"rule": "write-binding",
					"severity": "Info",
					"asset": e["target"],
					"edge": e["id"],
					"message": f"{nodes[e['source']]['title']} acts on {nodes[e['target']]['title']}",
				}
			)
	order = {"Critical": 0, "Warning": 1, "Info": 2}
	out.sort(key=lambda f: (order[f["severity"]], f["rule"], f["asset"]))
	return out


def trace(graph: Graph, start: str, direction: str = "downstream", max_depth: int = 12) -> dict:
	"""The lineage of one node: {"nodes": [ids in visit order], "edges": [edge ids], "depth": {id: n}}.

	downstream from a physical node: the equipment it contains, the signals bound to it, and
	everything those signals feed (connector, event stream, KPI, ERP record, report).
	upstream from a data node: what feeds it, back to the signals, and the physical assets those
	signals are measured at. This is the "which instruments does this KPI depend on" question
	asked for validation evidence and root cause."""
	if start not in graph.nodes:
		raise KeyError(start)
	if direction not in ("downstream", "upstream"):
		raise ValueError("direction must be downstream or upstream")
	bound_types = tuple(model.DIRECTIONS.values())
	depth = {start: 0}
	order = [start]
	used = []
	queue = deque([start])
	while queue:
		current = queue.popleft()
		if depth[current] >= max_depth:
			continue
		node = graph.nodes[current]
		steps = []
		if direction == "downstream":
			steps += [(e, e["target"]) for e in graph.out_edges(current, model.LINEAGE_TYPES)]
			if node["layer"] == model.PHYSICAL:
				steps += [(e, e["target"]) for e in graph.out_edges(current, ("Contains",))]
				steps += [(e, e["source"]) for e in graph.in_edges(current, bound_types + ("Runs On",))]
		else:
			steps += [(e, e["source"]) for e in graph.in_edges(current, model.LINEAGE_TYPES)]
			if node["layer"] == model.DATA:
				steps += [(e, e["target"]) for e in graph.out_edges(current, bound_types + ("Runs On",))]
		for edge, nxt in steps:
			if nxt not in graph.nodes:
				continue
			used.append(edge["id"])
			if nxt not in depth:
				depth[nxt] = depth[current] + 1
				order.append(nxt)
				queue.append(nxt)
	return {"start": start, "direction": direction, "nodes": order, "edges": sorted(set(used)), "depth": depth}


# Layout
# ------

PHYSICAL_ROW = 140
DATA_ROW = 110
COLUMN = 170


def layout(graph: Graph) -> dict:
	"""x, y for every node: the physical layer as a containment tree along the bottom, the data
	layer stacked above it, each data node over the physical nodes it is bound to or fed from.

	Deterministic (sorted by id at every step), so the picture does not jump between refreshes."""
	nodes = graph.nodes
	pos = {}
	physical = {k: v for k, v in nodes.items() if v["layer"] == model.PHYSICAL}
	children = defaultdict(list)
	for node in physical.values():
		if node["parent"] in physical:
			children[node["parent"]].append(node["id"])
	roots = sorted(k for k, v in physical.items() if v["parent"] not in physical)
	depth_of = {}
	next_x = [0]

	def place(node_id, depth, seen):
		if node_id in seen:  # a containment cycle; place it once and stop
			return pos.get(node_id, (0, 0))[0]
		seen.add(node_id)
		depth_of[node_id] = depth
		kids = sorted(children[node_id])
		if not kids:
			x = next_x[0]
			next_x[0] += COLUMN
		else:
			xs = [place(k, depth + 1, seen) for k in kids]
			x = (min(xs) + max(xs)) / 2
		pos[node_id] = (x, 0)
		return x

	seen = set()
	for root in roots:
		place(root, 0, seen)
	max_depth = max(depth_of.values(), default=0)
	data_rows = _data_depths(graph)
	data_height = (max(data_rows.values(), default=-1) + 1) * DATA_ROW
	for node_id, (x, _) in list(pos.items()):
		pos[node_id] = (x, data_height + 60 + depth_of[node_id] * PHYSICAL_ROW)

	bound_types = tuple(model.DIRECTIONS.values()) + ("Runs On",)
	rows = defaultdict(list)
	for node_id in sorted(data_rows, key=lambda n: (data_rows[n], n)):
		anchors = [pos[e["target"]][0] for e in graph.out_edges(node_id, bound_types) if e["target"] in pos]
		anchors += [pos[e["source"]][0] for e in graph.in_edges(node_id) if e["source"] in pos and e["source"] in data_rows]
		x = sum(anchors) / len(anchors) if anchors else next_x[0]
		if not anchors:
			next_x[0] += COLUMN
		row = data_rows[node_id]
		pos[node_id] = (x, data_height - (row + 1) * DATA_ROW + 30)
		rows[row].append(node_id)
	# Spread nodes on the same data row that landed on top of each other.
	for row, ids in rows.items():
		ids.sort(key=lambda n: (pos[n][0], n))
		last = None
		for node_id in ids:
			x, y = pos[node_id]
			if last is not None and x < last + COLUMN * 0.8:
				x = last + COLUMN * 0.8
			pos[node_id] = (x, y)
			last = x
	return {k: {"x": round(v[0], 1), "y": round(v[1], 1)} for k, v in pos.items()}


def _data_depths(graph: Graph) -> dict:
	"""Row of each data node: 0 for nodes fed by nothing in the data layer (signals, agents),
	then one more than the deepest node feeding it. Cycles are broken by visiting each node once."""
	data = {k for k, v in graph.nodes.items() if v["layer"] == model.DATA}
	preds = defaultdict(set)
	for e in graph.edges:
		if e["type"] in model.LINEAGE_TYPES and e["source"] in data and e["target"] in data:
			preds[e["target"]].add(e["source"])
	depths = {}

	def depth(n, stack):
		if n in depths:
			return depths[n]
		if n in stack:
			return 0
		stack.add(n)
		d = 1 + max((depth(p, stack) for p in sorted(preds[n])), default=-1)
		stack.discard(n)
		depths[n] = d
		return d

	for n in sorted(data):
		depth(n, set())
	return depths


# Exports
# -------


def graph_dict(graph: Graph, *, with_layout: bool = True, with_findings: bool = True) -> dict:
	out = {
		"as_of": graph.now.strftime("%Y-%m-%d %H:%M:%S"),
		"stale_after_seconds": graph.stale_after_seconds,
		"nodes": [graph.nodes[k] for k in sorted(graph.nodes)],
		"edges": sorted(graph.edges, key=lambda e: e["id"]),
		"tenants": sorted({n["tenant"] for n in graph.nodes.values() if n["tenant"]}),
		"providers": sorted({n["provider"] for n in graph.nodes.values() if n["provider"]}),
	}
	if with_layout:
		out["layout"] = layout(graph)
	if with_findings:
		out["findings"] = findings(graph)
	return out


def _mermaid_id(node_id: str, ids: dict) -> str:
	if node_id not in ids:
		ids[node_id] = f"n{len(ids)}"
	return ids[node_id]


def _mermaid_label(text: str) -> str:
	return str(text).replace('"', "#quot;").replace("\n", " ")


_MERMAID_EDGE = {
	model.PHYSICAL: "---",
	model.DATA: "-->",
	model.BINDING: "-.->",
}


def to_mermaid(graph: Graph, *, direction: str = "TB") -> str:
	"""Mermaid flowchart text: a Data subgraph over a Physical one, physical containment as nested
	subgraphs, bindings as dotted arrows labelled "measured at", "acts on" or "runs on".

	Node ids are replaced by n0, n1 … (Mermaid ids cannot hold the characters asset ids use) and
	the real id is kept in the label, so the text is stable for the same graph."""
	ids: dict = {}
	nodes = graph.nodes
	lines = [f"flowchart {direction}"]
	physical = {k: v for k, v in nodes.items() if v["layer"] == model.PHYSICAL}
	data = sorted(k for k, v in nodes.items() if v["layer"] == model.DATA)
	children = defaultdict(list)
	for node in physical.values():
		if node["parent"] in physical:
			children[node["parent"]].append(node["id"])

	def node_line(node_id, indent):
		node = nodes[node_id]
		label = _mermaid_label(f"{node['title']}<br/><small>{node['kind']} · {node['status']}</small>")
		shape = ('[("', '")]') if node["kind"] in ("Historian Point", "Dataset") else ('["', '"]')
		if node["kind"] in ("Agent", "Agent Task"):
			shape = ('(["', '"])')
		return f"{indent}{_mermaid_id(node_id, ids)}{shape[0]}{label}{shape[1]}:::{_status_class(node)}"

	if data:
		lines.append('  subgraph DATA["Data layer"]')
		for node_id in data:
			lines.append(node_line(node_id, "    "))
		lines.append("  end")

	def emit(node_id, indent, seen):
		if node_id in seen:
			return
		seen.add(node_id)
		kids = sorted(children[node_id])
		if kids:
			sub = _mermaid_id(node_id, ids)
			lines.append(f'{indent}subgraph {sub}_g["{_mermaid_label(nodes[node_id]["title"])}"]')
			lines.append(node_line(node_id, indent + "  "))
			for k in kids:
				emit(k, indent + "  ", seen)
			lines.append(f"{indent}end")
		else:
			lines.append(node_line(node_id, indent))

	if physical:
		lines.append('  subgraph PHYSICAL["Physical layer"]')
		seen = set()
		for root in sorted(k for k, v in physical.items() if v["parent"] not in physical):
			emit(root, "    ", seen)
		lines.append("  end")

	for e in sorted(graph.edges, key=lambda e: e["id"]):
		if e["type"] == "Contains" or e["source"] not in nodes or e["target"] not in nodes:
			continue
		arrow = _MERMAID_EDGE[e["layer"]]
		label = e["type"].lower()
		if e.get("tag"):
			label += f" {e['tag']}"
		lines.append(
			f"  {_mermaid_id(e['source'], ids)} {arrow}|{_mermaid_label(label)}| {_mermaid_id(e['target'], ids)}"
		)
	for status, color in model.STATUS_COLORS.items():
		text = "#222" if status == "Idle" else "#fff"
		lines.append(f"  classDef {status.lower()} fill:{color},color:{text},stroke:#333")
	lines.append(f"  classDef datastale fill:{model.HEALTH_COLORS[model.STALE]},color:#222,stroke:#333")
	return "\n".join(lines) + "\n"


def _status_class(node):
	if node["layer"] == model.DATA:
		if node.get("health") == model.STALE:
			return "datastale"
		if node.get("health") == model.FAULT:
			return "down"
	return node["status"].lower()


def to_grafana(graph: Graph) -> dict:
	"""{"nodes": [...], "edges": [...]} in the field names of Grafana's Node Graph panel.

	Point two Infinity (JSON) queries at /api/method/foames.foames_topology.api.grafana_nodes and
	…grafana_edges, or one at …grafana and pick nodes and edges with root selectors. Node colour is
	the physical status, the secondary stat is the data health, and detail__ fields show in the
	panel's context menu."""
	out_nodes = []
	for node_id in sorted(graph.nodes):
		n = graph.nodes[node_id]
		color = model.STATUS_COLORS.get(n["status"], model.STATUS_COLORS["Unknown"])
		if n["layer"] == model.DATA and n.get("health") in (model.STALE, model.FAULT):
			color = model.HEALTH_COLORS[n["health"]]
		out_nodes.append(
			{
				"id": node_id,
				"title": n["title"],
				"subtitle": f"{n['kind']} · {n['layer']}",
				"mainstat": n["status"],
				"secondarystat": n.get("health") or "",
				"color": color,
				"detail__layer": n["layer"],
				"detail__tenant": n["tenant"] or "",
				"detail__provider": n["provider"] or "",
				"detail__last_seen": str(n["last_seen"] or ""),
			}
		)
	out_edges = []
	for e in sorted(graph.edges, key=lambda e: e["id"]):
		if e["source"] not in graph.nodes or e["target"] not in graph.nodes:
			continue
		edge = {
			"id": e["id"],
			"source": e["source"],
			"target": e["target"],
			"mainstat": e["type"],
			"detail__layer": e["layer"],
		}
		if e["layer"] == model.BINDING:
			edge["strokeDasharray"] = "4 3"
		out_edges.append(edge)
	return {"nodes": out_nodes, "edges": out_edges}


def overlay(graph: Graph, physical_ids=None) -> dict:
	"""For a view that already draws the physical layer: per physical node, its data health and
	the signals bound to it with their value, unit, freshness and where their data goes next.

	physical_ids limits the answer to the nodes the view shows."""
	bound_types = tuple(model.DIRECTIONS.values())
	out = {}
	for node_id, node in graph.nodes.items():
		if node["layer"] != model.PHYSICAL:
			continue
		if physical_ids is not None and node_id not in physical_ids:
			continue
		signals = []
		for e in graph.in_edges(node_id, bound_types):
			s = graph.nodes.get(e["source"])
			if s is None:
				continue
			feeds = [graph.nodes[x["target"]]["title"] for x in graph.out_edges(s["id"], model.LINEAGE_TYPES) if x["target"] in graph.nodes]
			signals.append(
				{
					"id": s["id"],
					"title": s["title"],
					"direction": e.get("direction"),
					"tag": e.get("tag"),
					"unit": e.get("unit") or s.get("unit"),
					"value": s.get("last_value"),
					"last_seen": s["last_seen"],
					"health": s.get("health"),
					"provider": s["provider"],
					"feeds": sorted(feeds),
				}
			)
		signals.sort(key=lambda s: s["id"])
		out[node_id] = {
			"status": node["status"],
			"health": node.get("health"),
			"source_doctype": node["source_doctype"],
			"source_name": node["source_name"],
			"signals": signals,
		}
	return out
