# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

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
