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

"""The vocabulary of the topology graph: layers, kinds, link types and statuses. No Frappe needed.

The graph has two layers that share one set of node ids:

* the physical layer is what exists and how it is connected (sites, areas, lines, machines,
  P&ID equipment and instruments, hosts and network devices), joined by containment, pipes,
  wiring and network links;
* the data layer is what flows (signals, connectors, historian points, event streams, KPIs, ERP
  records, services, agents and their tasks), joined by data-flow, derivation and posting links.

A Signal Binding joins the two: a data node is measured at, or acts on, a physical node. An agent
runs on a host the same way. Everything else in this package is built on these lists, and the
DocType Select options are kept equal to them (test_graph checks that).
"""

PHYSICAL = "Physical"
DATA = "Data"
BINDING = "Binding"
LAYERS = (PHYSICAL, DATA)
EDGE_LAYERS = (PHYSICAL, DATA, BINDING)

PHYSICAL_KINDS = (
	"Site",
	"Area",
	"Line",
	"Machine",
	"Equipment",
	"Instrument",
	"Valve",
	"Piping",
	"Host",
	"Network Device",
)
DATA_KINDS = (
	"Signal",
	"Connector",
	"Historian Point",
	"Dataset",
	"Event Stream",
	"KPI",
	"ERP Record",
	"Report",
	"Service",
	"Agent",
	"Agent Task",
)
KINDS = PHYSICAL_KINDS + DATA_KINDS + ("Other",)

# Physical kinds that are expected to have at least one signal bound to them. A machine or an
# instrument without any is reported as unbound; a site or a pipe is not.
EXPECTS_SIGNALS = ("Machine", "Instrument", "Valve")

# Data kinds that report continuously, so a long silence means stale data. A KPI computed daily, an
# ERP record or a finished agent task is not stale just because nothing new arrived.
STREAMING_KINDS = ("Signal", "Historian Point", "Event Stream", "Connector")

# Link types, each with the layer it belongs to.
LINK_TYPES = {
	"Contains": PHYSICAL,
	"Pipe": PHYSICAL,
	"Wiring": PHYSICAL,
	"Network": PHYSICAL,
	"Material Flow": PHYSICAL,
	"Data Flow": DATA,
	"Derives": DATA,
	"Posts To": DATA,
	"Delegates": DATA,
	"Runs On": BINDING,
}
# The link types lineage follows. Containment is followed only from a physical node downwards, so
# a machine's trace includes the instruments mounted on it.
LINEAGE_TYPES = ("Data Flow", "Derives", "Posts To", "Delegates")

# Signal Binding directions and the edge label each one is drawn with.
DIRECTIONS = {"Read": "Measured At", "Write": "Acts On"}

STATUSES = (
	"Unknown",
	"OK",
	"Running",
	"Idle",
	"Down",
	"Setup",
	"Maintenance",
	"Stale",
	"Retired",
)

# Data health, the badge drawn on a node next to its physical status colour.
FRESH = "fresh"
STALE = "stale"
NO_DATA = "no data"
FAULT = "fault"

# Colours for views and exports. Physical status is the node colour, data health the badge.
STATUS_COLORS = {
	"Running": "#2e7d32",
	"OK": "#2e7d32",
	"Idle": "#f9a825",
	"Setup": "#1565c0",
	"Down": "#c62828",
	"Maintenance": "#6a1b9a",
	"Stale": "#9e9e9e",
	"Retired": "#424242",
	"Unknown": "#616161",
}
HEALTH_COLORS = {FRESH: "#2e7d32", STALE: "#f9a825", NO_DATA: "#9e9e9e", FAULT: "#c62828"}

# Providers the built-in sync writes as. A collector cannot report as one of them, so a plugin
# can never overwrite what FoaMES derives from its own records.
SYNC_PROVIDERS = ("foames-mes", "foames-pid", "foames-erp")


def kind_layer(kind: str) -> str | None:
	if kind in PHYSICAL_KINDS:
		return PHYSICAL
	if kind in DATA_KINDS:
		return DATA
	return None
