# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Puts the data layer on Floor View: the floor snapshot gains a "topology" section with, per
machine, its data health and the signals bound to it (and to the instruments on it).

Registered under foames_floor_snapshot_extensions. Floor View's "Data layer" toggle reads it;
agents reading the snapshot get it too. Does nothing for a user who cannot read Topology Asset."""

import frappe

from foames.foames_topology import graph as topo
from foames.foames_topology import model, store


def extend_snapshot(snapshot, since=None, now=None):
	if not frappe.has_permission("Topology Asset", "read"):
		return
	graph = store.load_graph()
	machines = {
		n["source_name"]: n["id"]
		for n in graph.nodes.values()
		if n["source_doctype"] == "Machine" and n["layer"] == model.PHYSICAL
	}
	if not machines:
		return
	section = {}
	for machine, node_id in machines.items():
		# The machine and everything on it: a P&ID instrument mounted on the machine counts.
		ids = {node_id}
		lineage = topo.trace(graph, node_id, "downstream", max_depth=6)
		ids.update(n for n in lineage["nodes"] if graph.nodes[n]["layer"] == model.PHYSICAL)
		over = topo.overlay(graph, ids)
		signals = [s for entry in over.values() for s in entry["signals"]]
		healths = [s["health"] for s in signals if s["health"]]
		section[machine] = {
			"asset": node_id,
			"signals": len(signals),
			"stale": sum(1 for h in healths if h == model.STALE),
			"no_data": sum(1 for h in healths if h == model.NO_DATA),
			"health": topo.worst_health(healths),
			"feeds": sorted({f for s in signals for f in s["feeds"]}),
			"detail": signals[:20],
		}
	snapshot["topology"] = section
