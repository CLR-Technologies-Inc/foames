# foames

[![GitHub stars](https://img.shields.io/github/stars/CLR-Technologies-Inc/foames?style=social)](https://github.com/CLR-Technologies-Inc/foames/stargazers)
[![DeepSource](https://app.deepsource.com/gh/CLR-Technologies-Inc/foames.svg/?label=code+coverage&show_trend=true&token=ty6pE08s0fkat2D9lQsrsSb6)](https://app.deepsource.com/gh/CLR-Technologies-Inc/foames/)
[![DeepSource](https://app.deepsource.com/gh/CLR-Technologies-Inc/foames.svg/?label=active+issues&show_trend=true&token=ty6pE08s0fkat2D9lQsrsSb6)](https://app.deepsource.com/gh/CLR-Technologies-Inc/foames/)
[![DeepSource](https://app.deepsource.com/gh/CLR-Technologies-Inc/foames.svg/?label=resolved+issues&show_trend=true&token=ty6pE08s0fkat2D9lQsrsSb6)](https://app.deepsource.com/gh/CLR-Technologies-Inc/foames/)

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
| FoaMES PID | The P&ID tag register (ISA-5.1 tags), DEXPI and CSV import, links from tags to live signals, the P&ID Viewer (see [docs/pid.md](docs/pid.md)) |

FoaMES records never use Link fields to ERP DocTypes. They store an `External Reference` (ERP system, reference type, external ID) and the matching adapter resolves it. An adapter is available only when its ERP can be reached from the site. Adapters are registered through the `foames_erp_adapters` hook, so other apps can add more. See [docs/adapters.md](docs/adapters.md).

Connectors start **read-only**. A new site runs in [read-only mode](docs/read-only-mode.md): every write to an ERP, another MES, SCADA or a historian, and every write an agent makes over MCP, waits for an authorised operator's electronic signature (meaning, reason, user, time) or is refused, and each step is logged against its work order, Job Card or process run in a hash-chained audit log. A plant approves each connector's writes when its change control is ready.

Which ERPs and other manufacturing systems have an adapter, and what each one reads, posts and needs, is described per vendor under [docs/vendors/](docs/vendors/README.md). Nothing in the core depends on any of them.

## Integrations

FoaMES reaches other systems only through adapters and gateway paths, so none of them is required and each can be added or removed without touching the core. How each one is set up is in its guide under [docs/vendors/](docs/vendors/README.md). What each vendor publishes about its API, what its terms allow FoaMES to write, and where each integration sits on the roadmap is in [docs/vendor-interoperability.md](docs/vendor-interoperability.md) (not legal advice).

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
| WireGuard | Native VPN transport with a read-only topology collector outside the app | [docs/vendors/wireguard/](docs/vendors/wireguard/README.md) |
| Bluesky and Tiled (NSLS-II) | Lab and beamline data acquisition, through a bridge outside the app | [docs/vendors/bluesky/](docs/vendors/bluesky/README.md) |
| Process historians: AVEVA PI (PI Web API), InfluxDB, Ignition Tag Historian, TimescaleDB and SQL historians | Historian, read-only, through a bridge outside the app | [docs/vendors/historian/](docs/vendors/historian/README.md) |
| FreeCAD | CAD, read-only document inspection, through a bridge outside the app | [docs/vendors/freecad/](docs/vendors/freecad/README.md) |
| Building automation (BMS / BAS) controllers and meters over BACnet/IP and Modbus TCP | Building management, read-only, through a gateway outside the app | [docs/building-management.md](docs/building-management.md) |

Any machine, PLC or SCADA system that can publish Sparkplug B, serve OPC UA, publish JSON over MQTT or post to a signed webhook can send machine data without a vendor-specific integration; see [docs/machine-data.md](docs/machine-data.md).

### Planned integrations

Not built yet; listed so contributors can see where help is wanted. Each would follow [docs/adapters.md](docs/adapters.md) and the "Adding a vendor" checklist in [foames/foames_adapters/AGENTS.md](foames/foames_adapters/AGENTS.md).

| Area | Systems |
| --- | --- |
| Other ERPs | Odoo; Microsoft Dynamics 365 (Business Central, Supply Chain Management); Epicor Kinetic; Infor CloudSuite and SyteLine; Oracle NetSuite and Fusion Cloud |
| Industrial data and SCADA | PTC Kepware and ThingWorx; AVEVA PI System beyond reading tag history (AF event frames as runs and batches); HighByte Intelligence Hub; Litmus Edge; Rockwell FactoryTalk Optix |
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
| [docs/recognition.md](docs/recognition.md) | Appreciating operators: kudos, credited ideas, milestones and weekly team highlights on the Floor View, with privacy controls |
| [docs/scheduling.md](docs/scheduling.md) | Finite-capacity production scheduling from shift calendars, maintenance and cycle times, with dispatching rules, a Gantt view and ERP demand |
| [docs/spc.md](docs/spc.md) | Control charts (I-MR, X-bar R) and Nelson / Western Electric run rules on machine measurements |
| [docs/life-sciences.md](docs/life-sciences.md) | Biopharma and medical device manufacturing: NPI stage gates and phase reviews, product requirements and tracing, MSAT tech transfer and comparability, PD simulation |
| [docs/validation.md](docs/validation.md) | Equipment qualification (IQ, OQ, PQ) and process validation (PPQ, CPV) with acceptance criteria, capability from machine data, evidence, deviations and requalification |
| [docs/dashboards.md](docs/dashboards.md) | Role workspaces, dashboards, number cards and the script reports (OEE trends, downtime Pareto, MTBF and MTTR, suggestions, outbox health, process throughput) |
| [docs/read-only-mode.md](docs/read-only-mode.md) | Read-only mode (RO mode): connectors read first, every write waits for an operator's electronic sign-off logged against its work order, and the approval path for regulated plants |
| [docs/sbom.md](docs/sbom.md) | The CycloneDX 1.7 SBOM and cryptography bill of materials published with every release |
| [docs/process-mining.md](docs/process-mining.md) | Event logs, discovery, conformance, XES and OCEL export |
| [docs/mcp.md](docs/mcp.md) | The MCP server: connecting Claude Desktop, Claude Code or any MCP client, the tools, permissions |
| [AGENTS.md](AGENTS.md) | For coding agents and developers building on FoaMES: invariants, hooks, API, tests |
| [docs/agents/floor-agent.md](docs/agents/floor-agent.md) | For an agent reading the floor and raising suggestions at run time |
| [docs/agents/equipment-agent/SKILL.md](docs/agents/equipment-agent/SKILL.md) | A skill for an agent that advises on machines by Equipment Complexity Level, within its model tier |
| [docs/agents/materials-agent/SKILL.md](docs/agents/materials-agent/SKILL.md) | A skill for an agent that watches lineside stock, dry lines, Q-time and floor life, and Material Processing Complexity |
| [docs/agents/research-to-code.md](docs/agents/research-to-code.md) | For an agent or developer turning a published method into a FoaMES change |
| [docs/agents/discovery/](docs/agents/discovery/README.md) | For an agent and a plant operator discovering, read-only, how a site's ERP, MES, SCADA or historian is set up before a connector is configured |
| [benchmarks/README.md](benchmarks/README.md) | A benchmark of coding agents on FoaMES tasks, with model recommendations by TRL and process complexity |

## Agent benchmark results

<!-- bench-status:start -->

Each agent runs the same tasks in the [agent benchmark](benchmarks/README.md): the six core tasks, and for the Claude Code agents the 29 sector case studies. Pass rate is the share of runs whose every invariant test passed. ECL reached is the highest Equipment Complexity Level at which the agent passed every task at that level and below, among the levels its model tier may claim. Off-label models were not built for agentic coding and are here to show how far each kind gets. Free tiers and the subscription cost $0; each dated report also gives the same tokens at list price.

**Claude Code on a Claude subscription (this account, not the API)**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| claude-code-haiku-5-5 | `claude-haiku-5-5` | agentic coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 94% | ECL 2 |
| claude-code-sonnet-5-5 | `claude-sonnet-5-5` | agentic coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 94% | none |
| claude-code-opus-5-5 | `claude-opus-5-5` | agentic coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 97% | ECL 2 |
| claude-code-fable-5-2 | `claude-fable-5-2` | agentic coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 97% | none |
| claude-code-opus-5 | `claude-opus-5` | agentic coding | Not run: older model, left out to stay inside the subscription's shared 5-hour usage limit | - | - | - |
| claude-code-opus-4-8 | `claude-opus-4-8` | agentic coding | Not run: older model, left out to stay inside the subscription's shared 5-hour usage limit | - | - | - |
| claude-code-sonnet-4-5 | `claude-sonnet-4-5` | agentic coding | Not run: older model, left out to stay inside the subscription's shared 5-hour usage limit | - | - | - |
| claude-code-haiku-4-5 | `claude-haiku-4-5` | agentic coding | Not run: older model, left out to stay inside the subscription's shared 5-hour usage limit | - | - | - |

**Google Gemini API, free tier**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-gemini-flash | `gemini/gemini-3.8-flash` | - | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 67% | none |

**OpenRouter, free models**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-openrouter-free | `openrouter/thinkingmachines/inkling-2-small:free` | - | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 50% | none |

**NVIDIA Build (NIM), free development credits**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-nvidia-deepseek | `nvidia_nim/deepseek-ai/deepseek-v4.1-flash` | coding and general | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 9 | 0% | none |
| aider-nvidia-kimi | picked at run time | agentic coding | Skipped: NVIDIA Build listed no Kimi model for this key on 2026-11-16 | - | - | - |
| aider-nvidia-glm | `nvidia_nim/z-ai/glm-5.3-flash` | agentic coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-nvidia-minimax | `nvidia_nim/minimaxai/minimax-m3.1-flash` | agentic coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 15 | 0% | none |
| aider-nvidia-qwen3-coder | picked at run time | coding | Skipped: NVIDIA Build listed no Qwen3-Coder model for this key on 2026-11-16 | - | - | - |
| aider-nvidia-gpt-oss-120b | `nvidia_nim/openai/gpt-oss-20b` | reasoning (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 3% | none |
| aider-nvidia-nemotron | `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b` | reasoning (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-nvidia-llama | `nvidia_nim/meta/llama-3.2-90b-vision-instruct` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 0% | none |
| aider-nvidia-mistral-large | `nvidia_nim/mistralai/mistral-large-4-1t-a52b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 0% | none |
| aider-nvidia-gemma | `nvidia_nim/google/gemma-4-31b-it` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 3% | none |
| aider-nvidia-laguna | `nvidia_nim/poolside/laguna-xs-2.1` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 0% | none |
| aider-nvidia-step | `nvidia_nim/stepfun-ai/step-5-preview` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 35 | 0% | none |

**Groq, free tier**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-groq-free | picked at run time | - | Skipped: Groq's free tier allowed at most 8,000 tokens a minute on every chat model it listed (2026-11-16), less than one aider request (about 12,700 tokens) | - | - | - |

**Mistral, free tier**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-mistral-devstral | `mistral/devstral-small-latest` | - | Skipped: the provider asked for a credit card at sign-up (2026-11-16), so it is not a no-cost tier for this benchmark | - | - | - |

**Cerebras, free tier**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-cerebras-gpt-oss-120b | `cerebras/gpt-oss-120b` | - | Skipped: the provider asked for a credit card at sign-up (2026-11-16), so it is not a no-cost tier for this benchmark | - | - | - |

**Ollama on a GitHub-hosted runner (4 vCPU, 16 GB, CPU only)**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-ollama-qwen2.5-coder-7b | `ollama_chat/qwen2.5-coder:7b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-qwen2.5-coder-14b | `ollama_chat/qwen2.5-coder:14b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-qwen3-8b | `ollama_chat/qwen3:8b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-qwen3-14b | `ollama_chat/qwen3:14b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-granite3.3-8b | `ollama_chat/granite3.3:8b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-gpt-oss-20b | `ollama_chat/gpt-oss:20b` | reasoning (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 17% | none |
| aider-ollama-deepseek-coder-v2-16b | `ollama_chat/deepseek-coder-v2:16b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-yi-coder-9b | `ollama_chat/yi-coder:9b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-granite-code-8b | `ollama_chat/granite-code:8b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-codegemma-7b | `ollama_chat/codegemma:7b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-deepcoder-14b | `ollama_chat/deepcoder:14b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-starcoder2-15b | `ollama_chat/starcoder2:15b` | coding (base model, not tuned for chat) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-qwen2.5-coder-1.5b | `ollama_chat/qwen2.5-coder:1.5b` | coding | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-llama3.1-8b | `ollama_chat/llama3.1:8b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-mistral-7b | `ollama_chat/mistral:7b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-mistral-nemo-12b | `ollama_chat/mistral-nemo:12b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-gemma3-12b | `ollama_chat/gemma3:12b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-phi4-14b | `ollama_chat/phi4:14b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-olmo2-13b | `ollama_chat/olmo2:13b` | general chat (fully open data) (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-falcon3-10b | `ollama_chat/falcon3:10b` | general chat (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-deepseek-r1-14b | `ollama_chat/deepseek-r1:14b` | reasoning (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-phi4-reasoning-14b | `ollama_chat/phi4-reasoning:14b` | reasoning (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-qwen3-4b | `ollama_chat/qwen3:4b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-qwen3-1.7b | `ollama_chat/qwen3:1.7b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-qwen3-0.6b | `ollama_chat/qwen3:0.6b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-phi4-mini-3.8b | `ollama_chat/phi4-mini:3.8b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-llama3.2-3b | `ollama_chat/llama3.2:3b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-gemma3-1b | `ollama_chat/gemma3:1b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-granite3.3-2b | `ollama_chat/granite3.3:2b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-smollm2-1.7b | `ollama_chat/smollm2:1.7b` | tiny (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-mathstral-7b | `ollama_chat/mathstral:7b` | domain: maths and science (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-deepscaler-1.5b | `ollama_chat/deepscaler:1.5b` | domain: maths reasoning (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-meditron-7b | `ollama_chat/meditron:7b` | domain: medicine (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |
| aider-ollama-sqlcoder-7b | `ollama_chat/sqlcoder:7b` | domain: SQL (off-label) | [2026-11-16](benchmarks/results/2026-11-16/README.md) | 6 | 0% | none |

**Ollama on a free notebook GPU (Kaggle or Colab)**

| Agent | Model | Built for | Report | Tasks run | Pass rate | ECL reached |
| --- | --- | --- | --- | ---: | ---: | --- |
| aider-ollama-qwen3-coder-30b | `ollama_chat/qwen3-coder:30b` | coding | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |
| aider-ollama-devstral-24b | `ollama_chat/devstral:24b` | coding | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |
| aider-ollama-gemma3-27b | `ollama_chat/gemma3:27b` | general chat (off-label) | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |
| aider-ollama-mistral-small3.2-24b | `ollama_chat/mistral-small3.2:24b` | general chat (off-label) | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |
| aider-ollama-magistral-24b | `ollama_chat/magistral:24b` | reasoning (off-label) | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |
| aider-ollama-qwq-32b | `ollama_chat/qwq:32b` | reasoning (off-label) | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |
| aider-ollama-deepseek-r1-32b | `ollama_chat/deepseek-r1:32b` | reasoning (off-label) | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |
| aider-ollama-qwen3-30b | `ollama_chat/qwen3:30b` | general chat (MoE, 3B active) (off-label) | Needs a GPU: run benchmarks/notebooks/foames-bench-gpu.ipynb on Kaggle or Colab (not run yet) | - | - | - |

<!-- bench-status:end -->

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
- The counter-delta, owed-count and coverage ideas follow public MES practice, including the [FactorySemantics MES](https://github.com/factorysemantics/factorysemantics-mes) design notes (Apache-2.0).
- Read-only mode, with connector writes signed off by an operator and logged against the work order so regulated plants can approve the rollout, was suggested by Ramakrishna Gampa.
- [Floorgraph](https://github.com/s1dharthpv/floorgraph) by [s1dharthpv](https://github.com/s1dharthpv) (MIT) is an earlier shop-floor execution app for ERPNext built in response to that issue. FoaMES is an independent implementation. If any Floorgraph code is ever reused, its MIT notice will ship with it.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Every source file carries an `SPDX-License-Identifier: Apache-2.0` header; [docs/licensing.md](docs/licensing.md) explains the headers and the license of each dependency.

Copyright 2026 CLR Technologies Inc. and contributors.

## Star History

<a href="https://www.star-history.com/#CLR-Technologies-Inc/foames&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=CLR-Technologies-Inc/foames&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=CLR-Technologies-Inc/foames&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=CLR-Technologies-Inc/foames&type=Date" />
  </picture>
</a>
