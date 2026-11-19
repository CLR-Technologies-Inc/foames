# Topology: the physical layer, the data layer over it, and live views

FoaMES keeps one topology graph of the plant and the systems around it, and generates every
topology view from it. Nobody draws or edits a diagram by hand: a view, a Mermaid diagram and a
Grafana Node Graph are all read from the same records, so they cannot drift apart.

## One graph, two layers

| Layer | What it holds | Joined by |
| --- | --- | --- |
| **Physical** | Sites, areas, lines, machines, P&ID equipment, instruments and valves, hosts and network devices | Part Of (containment), Pipe, Wiring, Network, Material Flow |
| **Data** | Signals (PLC tags, OPC UA nodes, Sparkplug metrics), connectors, historian points, datasets, event streams, KPIs, ERP records, reports, services, agents and agent tasks | Data Flow, Derives, Posts To, Delegates |

The two layers share node ids. A **Signal Binding** joins them: a signal is *measured at* a
physical asset (Read) or *acts on* one (Write). An agent *runs on* a host the same way. An
instrument tag such as `TT-101` is therefore both a physical instrument and a signal, and the
binding says which signal, through which provider, in which unit.

A Write binding is recorded so the view can show which equipment a signal or an agent's task
touches. FoaMES itself never writes to equipment.

## Records

| DocType | What it is |
| --- | --- |
| Topology Asset | One node: id (`machine:CNC-01`, `pid:TT-101`, `signal:opc-ua:ns=2;s=TT101`), layer, kind, Part Of, status, last seen, tenant, provider, and the FoaMES record it mirrors |
| Topology Link | One directed link between two assets, with its type; the layer follows from the type |
| Signal Binding | Signal → physical asset, direction, tag, unit, latest reading and its own stale threshold |
| Topology Tenant | A company or site whose records are kept apart |
| Topology Settings | Sync on or off, the default tenant, the stale threshold, whether KPIs and ERP records are included |

Records the sync or a collector writes are **Managed**. A record someone creates by hand is never
overwritten by either, so you can add or correct anything the sync does not know about.

## Keeping it current

**The built-in sync** runs every 15 minutes (and from **Sync now** on the Topology View page). It
mirrors what FoaMES already records:

- each Line (from Machine.line) contains its Machines;
- each machine data source in Machine Data Settings becomes a Signal bound to its machine, flowing
  through its Connector (OPC UA, Sparkplug B) into the machine's event stream;
- the event stream derives the machine's OEE KPI and posts to the ERP record (an External
  Reference) the machine is working on;
- when the P&ID module is installed, each P&ID component becomes a physical asset Part Of its
  parent component or machine, its process and signal lines become Pipe and Wiring links, and a
  component with a signal source gets a bound Signal (or Historian Point) of its own.

Anything the sync wrote before and no longer finds is **retired** (disabled, status Retired), not
deleted. A link or binding someone else made that still points at it shows up as drift.

**Collectors** add what FoaMES cannot see itself. They post a report to
`foames.foames_topology.api.ingest` (see below). Optional collectors ship in
[bridges/topology](../bridges/topology/README.md) for network hosts, native VPN interfaces and
peers ([deployment guide](vendors/wireguard/README.md)), and AI agent activity read from a JSON Lines log. Other apps
can register their own with the `foames_topology_collectors` hook.

## Isolation: tenants and providers

Every asset, link and binding carries a **tenant** (the company it belongs to; empty means shared
infrastructure) and a **provider** (the plugin, adapter or collector that reports it).

- Give a user a User Permission on Topology Tenant and every list, report and graph read shows
  them only their tenants' records plus shared ones. A user without such a restriction gets the
  combined view across tenants. Every view is read-only.
- A link or binding between two different tenants is refused when it is saved, and reported as a
  Critical finding if one appears anyway.
- A collector's report is stamped with its provider. A provider may only change assets it
  provides; assets another provider owns, assets made by hand and the built-in sync's assets are
  refused item by item. The sync's provider names (`foames-mes`, `foames-pid`, `foames-erp`)
  cannot be reported as.

## Views

**Topology View** (`/app/topology-view`) draws the physical layer as a containment tree along the
bottom and the data layer above it, each data node over the physical nodes it is bound to or fed
from. Toggle the physical layer, the data layer and the bindings; filter by tenant or provider.
Node colour is the physical status (running, idle, down, maintenance, retired); the badge is the
data health (fresh, stale, no data, fault). It refreshes every 30 seconds.

- Click a physical node to trace **downstream**: the equipment on it, the signals bound to it, and
  everything they feed, through connector, event stream and KPI to the ERP record.
- Click a data node to trace **upstream**: what feeds it, back to the signals and the physical
  instruments they are measured at. This answers "which instruments does this KPI depend on",
  for validation evidence and root cause.
- Shift-click opens the record.

**Floor View** has a **Data layer** button. With it on, each machine tile shows how many signals
are bound to the machine and the instruments on it, how many are stale or silent, and where their
data goes. The same section is in the floor snapshot (`topology`) for agents.

**Findings** under the graph list what is wrong or missing:

| Rule | Severity | Meaning |
| --- | --- | --- |
| cross-tenant | Critical | A link or binding joins two tenants |
| dangling | Warning | A link or binding points at an asset that is not in the register any more (drift) |
| stale | Warning | A signal has not reported within its threshold |
| unbound | Info | A machine, instrument or valve has no signal bound to it (a gap in the data layer) |
| write-binding | Info | A signal or agent task acts on a physical asset |

Only streaming kinds (signals, historian points, event streams, connectors) go stale; a daily KPI
or a finished agent task does not.

## API

All read endpoints take optional `tenant` (one or a comma-separated list), `layers` (`Physical`,
`Data` or both) and `provider`, and need read access to Topology Asset.

| Method | Returns |
| --- | --- |
| `foames.foames_topology.api.get_graph` | nodes, edges, layout, findings, the tenants and providers in view |
| `foames.foames_topology.api.get_mermaid` | Mermaid flowchart text; `direction` TB, LR … |
| `foames.foames_topology.api.grafana` | `{"nodes", "edges"}` in Grafana Node Graph field names |
| `foames.foames_topology.api.grafana_nodes`, `…grafana_edges` | the two arrays on their own |
| `foames.foames_topology.api.trace` | `asset`, `direction` (downstream or upstream): the lineage |
| `foames.foames_topology.api.overlay` | per physical asset, its status, data health and bound signals, by `assets` or by `source_doctype` and `source_names` |
| `foames.foames_topology.api.ingest` (POST) | write a collector report; FoaMES Integration, FoaMES Engineer or System Manager |
| `foames.foames_topology.api.sync_now` (POST) | run the sync now; FoaMES Engineer or System Manager |

`overlay` is for a view that already draws the physical layer and wants the data layer over it.
For a P&ID drawing, call it with `source_doctype=PID Component` and the components on the drawing;
the answer is keyed by component.

### Grafana

Grafana's Node Graph panel reads nodes and edges as two data frames. With the Infinity data source:

1. Add an Infinity data source pointing at your FoaMES site, with an API key and secret of a
   read-only user (`Authorization: token <key>:<secret>`).
2. Add a Node Graph panel with two queries, type JSON, URLs
   `/api/method/foames.foames_topology.api.grafana_nodes` and `…grafana_edges`, root selector
   `message`.
3. Set the refresh interval on the dashboard. Node colour, the secondary stat (data health) and the
   `detail__` fields (layer, tenant, provider, last seen) come from the graph.

Grafana's own dashboards can sit alongside: the historian bridge's databases and the Frappe
database are both sources Grafana can query directly.

### Collector report

```json
{
  "provider": "network-collector",
  "tenant": "Plant A",
  "assets":   [{"asset_id": "host:gw1", "kind": "Host", "status": "OK", "last_seen": "2026-11-15 12:00:00"}],
  "links":    [{"from_asset": "host:gw1", "to_asset": "network:plant", "link_type": "Network"}],
  "bindings": [{"signal": "signal:TT-101", "physical_asset": "pid:TT-101", "direction": "Read", "unit": "degC"}],
  "retire_missing": false
}
```

The layer follows from the kind when it is left out. Containment is `parent_asset` on the asset,
not a link. With `retire_missing`, the provider's assets, links and bindings that are not in the
report are retired, so a full report each run keeps the graph exact. The answer counts what was
inserted, updated, unchanged and skipped, and lists each refused item with its reason.

## Extending

- `foames_topology_collectors` (hooks.py): dotted paths called during the sync, each returning a
  collector report, checked like one posted to the API.
- `foames_floor_snapshot_extensions` already carries the Floor View data layer
  (`foames.foames_topology.floor.extend_snapshot`).
- The graph functions in `foames/foames_topology/graph.py` take plain lists of dicts and need no
  site, so another app or an agent can build, check, trace and export a graph of its own.
