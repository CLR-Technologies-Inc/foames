# FoaMES documentation

Start with [installation.md](installation.md), then the pages for the parts you use.

## Setting up

| Page | What it covers |
| --- | --- |
| [installation.md](installation.md) | Requirements, `bench` install, roles, scheduler, running the gateways under supervisor, first configuration, a smoke test, development setup |
| [dev-bench.md](dev-bench.md) | The Docker dev bench: the whole test suite locally on Frappe v15 or v16, with ERPNext optional |
| [erpnext-adapter.md](erpnext-adapter.md) | External References, the ERPNext adapter, running without an ERP, writing an adapter for another ERP |
| [s4hana-adapter.md](s4hana-adapter.md) | The SAP S/4HANA adapter: OData resolution, the posting outbox, inbound IDocs, setup on both sides, day-to-day operation |
| [machine-data.md](machine-data.md) | How machine events reach FoaMES: the signed webhook, MQTT, OPC UA and Sparkplug B, the event shape, counter rules |
| [ignition.md](ignition.md) | Connecting an Ignition SCADA gateway through Sparkplug B, OPC UA or a gateway script |

## Using

| Page | What it covers |
| --- | --- |
| [floor-view.md](floor-view.md) | The Floor View page, machine states, the downtime workflow, Agent Suggestions and the built-in rules, the floor snapshot |
| [oee.md](oee.md) | How OEE is computed, setting a machine up for it, shift patterns, the daily OEE Period, OEE on demand, a worked example |
| [andon.md](andon.md) | Andon calls: call types and their targets, the status flow, escalation into suggestions, the Floor View button, the API, the Andon Response report |
| [dashboards.md](dashboards.md) | The role workspaces, number cards, dashboard charts and the script reports: OEE by machine, line and shift, downtime Pareto, MTBF and MTTR, suggestion status, outbox health, process throughput, andon response |

## For agents and integrators

| Page | What it covers |
| --- | --- |
| [../AGENTS.md](../AGENTS.md) | The guide for coding agents and developers building on or integrating FoaMES: invariants, extension hooks, API surface, tests |
| [agents/floor-agent.md](agents/floor-agent.md) | The playbook for an agent that reads the floor snapshot and raises suggestions, with suggested MCP tool names |
