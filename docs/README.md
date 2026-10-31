# FoaMES documentation

Start with [installation.md](installation.md), then the pages for the parts you use.

## Setting up

| Page | What it covers |
| --- | --- |
| [installation.md](installation.md) | Requirements, `bench` install, roles, scheduler, running the gateways under supervisor, first configuration, a smoke test, development setup |
| [erpnext-adapter.md](erpnext-adapter.md) | External References, the ERPNext adapter, running without an ERP, writing an adapter for another ERP |
| [s4hana-adapter.md](s4hana-adapter.md) | The SAP S/4HANA adapter: OData resolution, the posting outbox, inbound IDocs, setup on both sides, day-to-day operation |
| [machine-data.md](machine-data.md) | How machine events reach FoaMES: the signed webhook, MQTT, OPC UA and Sparkplug B, the event shape, counter rules |
| [ignition.md](ignition.md) | Connecting an Ignition SCADA gateway through Sparkplug B, OPC UA or a gateway script |

## Using

| Page | What it covers |
| --- | --- |
| [floor-view.md](floor-view.md) | The Floor View page, machine states, the downtime workflow, Agent Suggestions and the built-in rules, the floor snapshot |
| [oee.md](oee.md) | How OEE is computed, setting a machine up for it, the daily OEE Period, OEE on demand, a worked example |

## For agents and integrators

| Page | What it covers |
| --- | --- |
| [../AGENTS.md](../AGENTS.md) | The guide for coding agents and developers building on or integrating FoaMES: invariants, extension hooks, API surface, tests |
| [mcp.md](mcp.md) | The MCP server: connecting Claude Desktop, Claude Code or any MCP client with an API key, the 23 tools, permissions, limits |
| [agents/floor-agent.md](agents/floor-agent.md) | The playbook for an agent that reads the floor snapshot and raises suggestions, with the MCP tool names |
