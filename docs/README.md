# FoaMES documentation

Start with [installation.md](installation.md), then the pages for the parts you use.

## Setting up

| Page | What it covers |
| --- | --- |
| [installation.md](installation.md) | Requirements, `bench` install, roles, scheduler, running the gateways under supervisor, first configuration, a smoke test, development setup |
| [dev-bench.md](dev-bench.md) | The Docker dev bench: the whole test suite locally on Frappe v15 or v16, with ERPNext optional |
| [machine-data.md](machine-data.md) | How machine events reach FoaMES: the signed webhook, MQTT, OPC UA and Sparkplug B, the event shape, counter rules |
| [sbom.md](sbom.md) | The CycloneDX 1.7 SBOM: where to get it, what is in it (dependencies, the cryptography bill of materials, connected services), building and validating it |

## Vendors

Vendor-specific guides, one folder per vendor. See [vendors/](vendors/README.md) for the index and how to add one.

| Page | What it covers |
| --- | --- |
| [vendors/s4hana/](vendors/s4hana/README.md) | The SAP S/4HANA adapter: OData resolution, the posting outbox, inbound IDocs, setup on both sides ([setup](vendors/s4hana/setup.md)), postings ([postings](vendors/s4hana/postings.md)), day-to-day operation |
| [vendors/erpnext/](vendors/erpnext/README.md) | External References, the ERPNext adapter, running without an ERP, writing an adapter for another ERP |
| [vendors/ignition/](vendors/ignition/README.md) | Connecting an Ignition SCADA gateway through Sparkplug B, OPC UA or a gateway script |

## Using

| Page | What it covers |
| --- | --- |
| [floor-view.md](floor-view.md) | The Floor View page, machine states, the downtime workflow, Agent Suggestions and the built-in rules, the floor snapshot |
| [oee.md](oee.md) | How OEE is computed, setting a machine up for it, shift patterns, the daily OEE Period, OEE on demand, a worked example |
| [andon.md](andon.md) | Andon calls: call types and their targets, the status flow, escalation into suggestions, the Floor View button, the API, the Andon Response report |
| [maintenance.md](maintenance.md) | Preventive maintenance: plans by calendar, run hours or counts, work orders, the hourly check and its suggestions, the Maintenance Due List |
| [dashboards.md](dashboards.md) | The role workspaces, number cards, dashboard charts and the script reports: OEE by machine, line and shift, downtime Pareto, MTBF and MTTR, suggestion status, outbox health, process throughput, andon response, the maintenance due list |

## For agents and integrators

| Page | What it covers |
| --- | --- |
| [../AGENTS.md](../AGENTS.md) | The guide for coding agents and developers building on or integrating FoaMES: invariants, extension hooks, API surface, tests |
| [mcp.md](mcp.md) | The MCP server: connecting Claude Desktop, Claude Code or any MCP client with an API key, the 24 tools, permissions, limits |
| [agents/floor-agent.md](agents/floor-agent.md) | The playbook for an agent that reads the floor snapshot and raises suggestions, with the MCP tool names |
| [agents/research-to-code.md](agents/research-to-code.md) | The playbook for turning a public paper into a FoaMES change: sourcing rules, go or no-go triage, data mapping, invariant check, landing zones, test-first from the paper; [research-to-code-example.md](agents/research-to-code-example.md) is a worked run |
