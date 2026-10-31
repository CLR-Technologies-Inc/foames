# foames
Free Opensource Agentic MES

FOA MES is intended to be the visual technical MES you've always wanted. Simplified views over standard shop operations, integrated yields, core visuals in dashboards...WHAT A DREAM! 
Thanks for requirements and added some of my own. 
Intended for the Frappe ERP Next ecosystem, and designed with humans in mind. 

Other information is included in this project as a one stop shop for engineers looking LEAN, Six Sigma, SPC, and other manufacturing analytical tools, as they may eventually disappear from the internet.

## Architecture

FoaMES is a single Frappe app that depends on the Frappe framework only. ERP systems are optional and are reached through adapters, so the same core can run with ERPNext, with another ERP, or with no ERP at all.

| Module | What it holds |
| --- | --- |
| FoaMES Kernel | The shared records every FoaMES product builds on, plus `External Reference` (a pointer to a record in an ERP) and `FoaMES Settings` |
| FoaMES MES | Shop-floor execution: monitoring, downtime, OEE and machine data |
| FoaMES Adapters | The ERP adapter contract, the ERPNext adapter and the SAP S/4HANA adapter |
| FoaMES Process Mining | Event logs from FoaMES and ERP records, XES and OCEL export, discovery, performance and conformance analysis |

FoaMES records never use Link fields to ERP DocTypes. They store an `External Reference` (ERP system, reference type, external ID) and the matching adapter resolves it. The ERPNext adapter activates only when ERPNext is installed on the same site. Other apps can register more adapters through the `foames_erp_adapters` hook.

The ERPNext adapter resolves references with their details (a Work Order with its operations and required items, a BOM with its items and operations, a Job Card with its time logs), writes to ERPNext through the **ERPNext Outbox** (Stock Entries against a Work Order, Job Card time logs, Work Order stop, resume and close) with idempotency keys, document markers, sequence groups and retries, keeps External References current from ERPNext document events, puts each machine's open Job Cards on the floor, and rolls each machine's good and scrap counts and running time up to the Job Card it is working on. See [docs/erpnext-adapter.md](docs/erpnext-adapter.md).

The SAP S/4HANA adapter is remote: it resolves references over S/4HANA's released OData APIs, sends postings through an outbox with idempotency keys and retries, and receives IDocs over HTTP. It does not use RFC. Setup and licensing notes are in [docs/s4hana-adapter.md](docs/s4hana-adapter.md).

## Installation

FoaMES supports Frappe v15 and v16. ERPNext is optional.

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/CLR-Technologies-Inc/foames
bench --site $SITE install-app foames
```

The full guide, including roles, the scheduler, running the gateways and a smoke test, is [docs/installation.md](docs/installation.md).

## Documentation

| Page | Covers |
| --- | --- |
| [docs/installation.md](docs/installation.md) | Install, update, roles, scheduler, gateways under supervisor, first configuration, development setup |
| [docs/dev-bench.md](docs/dev-bench.md) | A Docker dev bench that runs the whole test suite locally, with Frappe v15 or v16 and ERPNext optional |
| [docs/erpnext-adapter.md](docs/erpnext-adapter.md) | External References, the ERPNext adapter, running without an ERP, writing an adapter |
| [docs/s4hana-adapter.md](docs/s4hana-adapter.md) | The SAP S/4HANA adapter: setup on both sides, the outbox, inbound IDocs, operation |
| [docs/machine-data.md](docs/machine-data.md) | The webhook, MQTT, OPC UA and Sparkplug B paths and the event shape |
| [docs/ignition.md](docs/ignition.md) | Connecting Ignition SCADA |
| [docs/floor-view.md](docs/floor-view.md) | The Floor View, downtime and Agent Suggestions |
| [docs/oee.md](docs/oee.md) | How OEE is computed and how to set a machine up for it |
| [docs/dashboards.md](docs/dashboards.md) | Role workspaces, dashboards, number cards and the script reports (OEE trends, downtime Pareto, MTBF and MTTR, suggestions, outbox health, process throughput) |
| [docs/process-mining.md](docs/process-mining.md) | Event logs, discovery, conformance, XES and OCEL export |
| [docs/mcp.md](docs/mcp.md) | The MCP server: connecting Claude Desktop, Claude Code or any MCP client, the tools, permissions |
| [AGENTS.md](AGENTS.md) | For coding agents and developers building on FoaMES: invariants, hooks, API, tests |
| [docs/agents/floor-agent.md](docs/agents/floor-agent.md) | For an agent reading the floor and raising suggestions at run time |

## Contributing

Contributions need a signed Contributor License Agreement. See [CONTRIBUTING.md](CONTRIBUTING.md).

This app uses `pre-commit` for formatting and linting (ruff, eslint, prettier):

```bash
cd apps/foames
pre-commit install
```

GitHub Actions runs the tests on Frappe v15 and v16 without an ERP, and on Frappe v16 with ERPNext. The same matrix runs locally in Docker with the [dev bench](docs/dev-bench.md) (`cd docker && ./bench.sh up && ./bench.sh test`). It also runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

## Prior art and credits

- [frappe/erpnext#50827](https://github.com/frappe/erpnext/issues/50827) asked for real-time machine monitoring, plant floor visibility, downtime tracking, OEE, work order and job card tracking, and PLC/IoT integration in ERPNext. It was closed as a product in its own right, and FoaMES takes up that requirement list.
- [Floorgraph](https://github.com/s1dharthpv/floorgraph) by [s1dharthpv](https://github.com/s1dharthpv) (MIT) is an earlier shop-floor execution app for ERPNext built in response to that issue. FoaMES is an independent implementation. If any Floorgraph code is ever reused, its MIT notice will ship with it.

## Machine data

| Record | Module | Role |
| --- | --- | --- |
| Machine | MES | A machine that reports events, with its state, last-seen time, counter rollover and OEE parameters. |
| Machine Event | MES | One event from a machine (state, count, measurement, alarm, message), processed into state, downtime and counter deltas. |
| Downtime Reason, Downtime Record | MES | Downtime opened and closed automatically from machine state, with a reason an operator assigns. |
| Machine Data Settings | MES | Webhook secret, MQTT broker, Sparkplug B group, OPC UA endpoint, the node and metric map, staleness threshold. |

Events arrive through a signed webhook, an MQTT gateway, a Sparkplug B gateway or an OPC UA gateway. Ignition SCADA connects through any of the three machine-data paths it supports (Sparkplug B via MQTT Transmission, its OPC UA server, or a gateway script posting to the webhook); see [docs/ignition.md](docs/ignition.md). Counter readings become deltas, and a first, reset or out-of-order reading never invents production. See [docs/machine-data.md](docs/machine-data.md), including the hook other apps use to act on processed events.

## OEE, the floor view and agent suggestions

| Record or page | Module | Role |
| --- | --- | --- |
| OEE Period | MES | OEE for a machine over a period from its events, downtime and counts. Planned downtime is excluded from availability; time without a machine signal is counted as loss, never as run time. One period per machine per day is computed by the scheduler over the machine's scheduled shift. |
| Floor View (page) | MES | Live tiles per machine with state, counts and OEE, plus open suggestions. |
| Agent Suggestion | MES | A finding raised by the built-in rules or by an external agent, with evidence, for a person to accept or dismiss. |

The OEE arithmetic and the suggestion rules have no Frappe dependency (`foames/foames_mes/oee.py`, `suggestions.py`). The counter-delta, owed-count and coverage ideas follow public MES practice, including the FactorySemantics MES design notes. See [docs/agents/floor-agent.md](docs/agents/floor-agent.md) for the agent API and the hooks that add snapshot sections and rules.

## Process mining

| Record | Module | Role |
| --- | --- | --- |
| Event Log Source | Process Mining | A field map that turns any DocType's records into events (case, activity, timestamps, resource, objects). ERP records are named as text and skipped when not installed. |
| Process Event Log | Process Mining | A saved extraction over a window and chosen sources, with discovery, conformance against another log, and XES or OCEL 2.0 export from the form. |

Machine states and downtime are built-in sources. The analyses (directly-follows graph, variants, throughput, waiting times, rework, conformance replay and footprint comparison) have no Frappe dependency (`foames/foames_process_mining/discovery.py`, `conformance.py`). See [docs/process-mining.md](docs/process-mining.md).

## Agents and MCP

FoaMES is an MCP server. `POST /api/method/foames.foames_mcp.api.mcp` speaks the Model Context Protocol over Streamable HTTP with a Frappe API key, and `python -m foames.foames_mcp` is a standard-library stdio bridge to it for Claude Desktop, Claude Code, Cursor and other clients. The 24 tools read machines and state, downtime, OEE, the floor snapshot, suggestions, process mining and ERP references through the adapters, each with the permissions of the key's user; the only writes create Agent Suggestions or record a machine's current job. See [docs/mcp.md](docs/mcp.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Copyright 2026 CLR Technologies Inc.
