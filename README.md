# foames
Free Opensource Agentic MES

FOA MES is intended to be the visual technical MES you've always wanted. Simplified views over standard shop operations, integrated yields, core visuals in dashboards...WHAT A DREAM! 
Thanks for requirements and added some of my own. 
Intended for the Frappe ERP Next ecosystem, and designed with humans in mind. 

Other information is included in this project as a one stop shop for engineers looking LEAN, Six Sigma, SPC, and other manufacturing analytical tools, as they may eventually disappear from the internet.

## Architecture

FoaMES is a single Frappe app that depends on the Frappe framework only. ERP systems are optional and are reached through adapters, so the same core can run with any ERP that has an adapter, or with no ERP at all.

| Module | What it holds |
| --- | --- |
| FoaMES Kernel | The shared records every FoaMES product builds on, plus `External Reference` (a pointer to a record in an ERP) and `FoaMES Settings` |
| FoaMES MES | Shop-floor execution: monitoring, downtime, OEE and machine data |
| FoaMES Adapters | The adapter contract and registry, and one adapter per supported ERP, MES or other manufacturing system (see [docs/vendors/](docs/vendors/README.md)) |
| FoaMES Process Mining | Event logs from FoaMES and ERP records, XES and OCEL export, discovery, performance and conformance analysis |

FoaMES records never use Link fields to ERP DocTypes. They store an `External Reference` (ERP system, reference type, external ID) and the matching adapter resolves it. An adapter is available only when its ERP can be reached from the site. Adapters are registered through the `foames_erp_adapters` hook, so other apps can add more. See [docs/adapters.md](docs/adapters.md).

Which ERPs and other manufacturing systems have an adapter, and what each one reads, posts and needs, is described per vendor under [docs/vendors/](docs/vendors/README.md). Nothing in the core depends on any of them.

## Integrations

FoaMES reaches other systems only through adapters and gateway paths, so none of them is required and each can be added or removed without touching the core. How each one is set up is in its guide under [docs/vendors/](docs/vendors/README.md).

### Existing alpha integrations

These ship in the app today. They are **alpha**: built against the vendors' published interfaces and covered by automated tests against in-memory stand-ins (ERPNext against a real ERPNext test site), but treat each as unproven until it has been run against your own system.

| Integration | Kind | Guide |
| --- | --- | --- |
| ERPNext | ERP, same site | [docs/vendors/erpnext/](docs/vendors/erpnext/README.md) |
| SAP S/4HANA | ERP, remote (OData, IDoc) | [docs/vendors/s4hana/](docs/vendors/s4hana/README.md) |
| Siemens Insights Hub (Opcenter Intelligence) | Industrial data platform | [docs/vendors/insights_hub/](docs/vendors/insights_hub/README.md) |
| Rockwell Plex Smart Manufacturing Platform | MES / ERP (REST profile) | [docs/vendors/plex/](docs/vendors/plex/README.md) |
| Rockwell FactoryTalk ProductionCentre and PharmaSuite | MES (REST profile) | [docs/vendors/factorytalk_productioncentre/](docs/vendors/factorytalk_productioncentre/README.md) |
| SAP Digital Manufacturing | MES (REST profile) | [docs/vendors/sap_dmc/](docs/vendors/sap_dmc/README.md) |
| Dassault Systèmes DELMIA Apriso | MES / MOM (REST profile) | [docs/vendors/delmia_apriso/](docs/vendors/delmia_apriso/README.md) |
| AVEVA Manufacturing Execution System | MES (REST profile) | [docs/vendors/aveva_mes/](docs/vendors/aveva_mes/README.md) |
| Critical Manufacturing MES | MES (REST profile) | [docs/vendors/critical_manufacturing/](docs/vendors/critical_manufacturing/README.md) |
| Tulip | Frontline operations platform (REST profile) | [docs/vendors/tulip/](docs/vendors/tulip/README.md) |
| Aegis FactoryLogix | MES (REST profile) | [docs/vendors/aegis_factorylogix/](docs/vendors/aegis_factorylogix/README.md) |
| Körber Werum PAS-X MES | MES (REST profile) | [docs/vendors/koerber_pasx/](docs/vendors/koerber_pasx/README.md) |
| Proficy Smart Factory MES (Velotic) | MES (REST profile) | [docs/vendors/proficy/](docs/vendors/proficy/README.md) |
| Ignition (Inductive Automation) | SCADA, through Sparkplug B, OPC UA or a gateway script | [docs/vendors/ignition/](docs/vendors/ignition/README.md) |

Any machine, PLC or SCADA system that can publish Sparkplug B, serve OPC UA, publish JSON over MQTT or post to a signed webhook can send machine data without a vendor-specific integration; see [docs/machine-data.md](docs/machine-data.md).

### Planned integrations

Not built yet; listed so contributors can see where help is wanted. Each would follow [docs/adapters.md](docs/adapters.md) and the "Adding a vendor" checklist in [foames/foames_adapters/AGENTS.md](foames/foames_adapters/AGENTS.md).

| Area | Systems |
| --- | --- |
| Other ERPs | Odoo; Microsoft Dynamics 365 (Business Central, Supply Chain Management); Epicor Kinetic; Infor CloudSuite and SyteLine; Oracle NetSuite and Fusion Cloud |
| Industrial data and SCADA | PTC Kepware and ThingWorx; AVEVA PI System; HighByte Intelligence Hub; Litmus Edge; Rockwell FactoryTalk Optix |
| Maintenance (CMMS) | IBM Maximo; SAP Plant Maintenance; Fiix; UpKeep |

To propose another, open an issue or a pull request.

## Installation

FoaMES supports Frappe v15 and v16. No ERP is required.

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/CLR-Technologies-Inc/foames
bench --site $SITE install-app foames
```

The full guide, including roles, the scheduler, running the gateways and a smoke test, is [docs/installation.md](docs/installation.md).

## Documentation

| Page | Covers |
| --- | --- |
| [docs/overview.md](docs/overview.md) | What FoaMES records, area by area: machine data, OEE and the floor, suggestions and andon, process mining, agents and MCP |
| [docs/installation.md](docs/installation.md) | Install, update, roles, scheduler, gateways under supervisor, first configuration, development setup |
| [docs/dev-bench.md](docs/dev-bench.md) | A Docker dev bench that runs the whole test suite locally, with Frappe v15 or v16 and an optional ERP app |
| [docs/adapters.md](docs/adapters.md) | External References, running without an ERP, writing an adapter for another ERP |
| [docs/vendors/](docs/vendors/README.md) | One guide folder per vendor: its ERP adapter or SCADA connection, setup and operation |
| [docs/machine-data.md](docs/machine-data.md) | The webhook, MQTT, OPC UA and Sparkplug B paths and the event shape |
| [docs/floor-view.md](docs/floor-view.md) | The Floor View, downtime and Agent Suggestions |
| [docs/oee.md](docs/oee.md) | How OEE is computed, shift patterns, and how to set a machine up for it |
| [docs/andon.md](docs/andon.md) | Andon calls for help at a machine: call types and targets, escalation, the API, the response report |
| [docs/spc.md](docs/spc.md) | Control charts (I-MR, X-bar R) and Nelson / Western Electric run rules on machine measurements |
| [docs/dashboards.md](docs/dashboards.md) | Role workspaces, dashboards, number cards and the script reports (OEE trends, downtime Pareto, MTBF and MTTR, suggestions, outbox health, process throughput) |
| [docs/sbom.md](docs/sbom.md) | The CycloneDX 1.7 SBOM and cryptography bill of materials published with every release |
| [docs/process-mining.md](docs/process-mining.md) | Event logs, discovery, conformance, XES and OCEL export |
| [docs/mcp.md](docs/mcp.md) | The MCP server: connecting Claude Desktop, Claude Code or any MCP client, the tools, permissions |
| [AGENTS.md](AGENTS.md) | For coding agents and developers building on FoaMES: invariants, hooks, API, tests |
| [docs/agents/floor-agent.md](docs/agents/floor-agent.md) | For an agent reading the floor and raising suggestions at run time |
| [docs/agents/research-to-code.md](docs/agents/research-to-code.md) | For an agent or developer turning a published method into a FoaMES change |
| [benchmarks/README.md](benchmarks/README.md) | A benchmark of coding agents on FoaMES tasks, with model recommendations by TRL and process complexity |

## Contributing

Contributions need a signed Contributor License Agreement. See [CONTRIBUTING.md](CONTRIBUTING.md).

This app uses `pre-commit` for formatting and linting (ruff, eslint, prettier):

```bash
cd apps/foames
pre-commit install
```

GitHub Actions runs the tests on Frappe v15 and v16 without an ERP, and on Frappe v16 with an ERP app installed. The same matrix runs locally in Docker with the [dev bench](docs/dev-bench.md) (`cd docker && ./bench.sh up && ./bench.sh test`). It also runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request, and builds a [CycloneDX 1.7 SBOM](docs/sbom.md) for each Frappe line that is attached to every release.

## Prior art and credits

- [frappe/erpnext#50827](https://github.com/frappe/erpnext/issues/50827) asked for real-time machine monitoring, plant floor visibility, downtime tracking, OEE, work order and job card tracking, and PLC/IoT integration in ERPNext. It was closed as a product in its own right, and FoaMES takes up that requirement list.
- The counter-delta, owed-count and coverage ideas follow public MES practice, including the FactorySemantics MES design notes.
- [Floorgraph](https://github.com/s1dharthpv/floorgraph) by [s1dharthpv](https://github.com/s1dharthpv) (MIT) is an earlier shop-floor execution app for ERPNext built in response to that issue. FoaMES is an independent implementation. If any Floorgraph code is ever reused, its MIT notice will ship with it.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Copyright 2026 CLR Technologies Inc.
