# FoaMES documentation

Start with [overview.md](overview.md) for what FoaMES records, then [installation.md](installation.md), then the pages for the parts you use.

## Setting up

| Page | What it covers |
| --- | --- |
| [installation.md](installation.md) | Requirements, `bench` install, roles, scheduler, running the gateways under supervisor, first configuration, a smoke test, development setup |
| [dev-bench.md](dev-bench.md) | The Docker dev bench: the whole test suite locally on Frappe v15 or v16, with an optional ERP app |
| [adapters.md](adapters.md) | External References, running without an ERP, writing an adapter for another ERP (vendor-neutral) |
| [machine-data.md](machine-data.md) | How machine events reach FoaMES: the signed webhook, MQTT, OPC UA and Sparkplug B, the event shape, counter rules |
| [read-only-mode.md](read-only-mode.md) | Read-only mode: connectors read first, every write waits for an operator's electronic sign-off or is refused, the hash-chained Write Audit Log against work orders and Job Cards, and the approval path for a regulated (21 CFR Part 11-style) plant |
| [sbom.md](sbom.md) | The CycloneDX 1.7 SBOM: where to get it, what is in it (dependencies, the cryptography bill of materials, connected services), building and validating it |
| [licensing.md](licensing.md) | The Apache-2.0 license, the source file header, and the license of each dependency and borrowed idea |

## Vendors

| Page | What it covers |
| --- | --- |
| [vendors/](vendors/README.md) | One folder per vendor, for its ERP adapter or SCADA connection: setup, operation, endpoints. The index lists what ships and how to add one. |

## Using

| Page | What it covers |
| --- | --- |
| [floor-view.md](floor-view.md) | The Floor View page, machine states, the downtime workflow, Agent Suggestions and the built-in rules, the floor snapshot |
| [oee.md](oee.md) | How OEE is computed, setting a machine up for it, shift patterns, the daily OEE Period, OEE on demand, a worked example |
| [andon.md](andon.md) | Andon calls: call types and their targets, the status flow, escalation into suggestions, the Floor View button, the API, the Andon Response report |
| [cycle-time.md](cycle-time.md) | Automatic and manual time: Cycle Time Standards, projections for a quantity, automation scenarios and their savings, the batch API for a scheduler, comparing a standard with what the machine did |
| [recognition.md](recognition.md) | Appreciating operators: kudos, credited ideas, milestones, weekly team highlights per line, the Floor View section, privacy and opt-out |
| [work-instructions.md](work-instructions.md) | Work instructions: writing and releasing revisions, step captures and limits, sign-offs and holds, running them from the Floor View, readings into SPC, the suggestions, the API |
| [pfmea.md](pfmea.md) | Process FMEA: failure chains rated by severity, occurrence and detection, the AIAG-VDA action priority, actions and re-rating, the observed occurrence from scrap counters, downtime and SPC, the daily check and its suggestions, the risk register and control plan reports |
| [scheduling.md](scheduling.md) | Production scheduling: finite-capacity plans from shift calendars, maintenance and cycle times, dispatching rules, publishing, the Gantt view, the behind-schedule rule, demand from an ERP and cycle-time hooks |
| [maintenance.md](maintenance.md) | Preventive maintenance: plans by calendar, run hours or counts, work orders, the hourly check and its suggestions, the Maintenance Due List |
| [topology.md](topology.md) | The topology graph: the physical layer, the data layer over it and Signal Bindings, the sync, collectors, tenant and provider isolation, Topology View, the Floor View data layer, findings, Mermaid and Grafana exports |
| [pid.md](pid.md) | P&IDs: the tag register and ISA-5.1 tags, DEXPI and CSV import, linking tags to live signals, the P&ID Viewer, the instrument-signal rule, the agent tools |
| [ehs.md](ehs.md) | Environmental health and safety: incidents and near misses with calculated recordability, permits to work and the running-under-lockout check, hazard assessments, exposure monitoring, the hourly check, incident rates |
| [commissioning.md](commissioning.md) | Equipment commissioning: packages, FAT and SAT with signed steps, loop checks, the A/B/C punch list, handover readiness and acceptance, the daily suggestions, the Punch List and Commissioning Status reports |
| [spc.md](spc.md) | Control charts and run rules on machine measurements, and the suggestions they raise |
| [validation.md](validation.md) | Equipment qualification (IQ, OQ, PQ) and process validation (PPQ, CPV): protocols, acceptance criteria, capability from machine data, executions with evidence and deviations, approval, requalification |
| [sops.md](sops.md) | Standard operating procedures as controlled documents: revisions, sign-off, effective dates, periodic review, operator acknowledgement and training, the SOP Training Matrix |
| [dashboards.md](dashboards.md) | The role workspaces, number cards, dashboard charts and the script reports: OEE by machine, line and shift, downtime Pareto, MTBF and MTTR, suggestion status, outbox health, process throughput, andon response, the maintenance due list |
| [risk-management.md](risk-management.md) | Enterprise risk management: the risk register, inherent and residual ratings, responses, tolerance and appetite, the hierarchy of controls with verification and effectiveness, templates, links to hazard assessments, PFMEAs, SOPs and maintenance, the daily check, the register and heat map |

## For agents and integrators

| Page | What it covers |
| --- | --- |
| [../AGENTS.md](../AGENTS.md) | The guide for coding agents and developers building on or integrating FoaMES: invariants, extension hooks, API surface, tests |
| [mcp.md](mcp.md) | The MCP server: connecting Claude Desktop, Claude Code or any MCP client with an API key, the 35 tools, permissions, limits |
| [agents/floor-agent.md](agents/floor-agent.md) | The playbook for an agent that reads the floor snapshot and raises suggestions, with the MCP tool names |
| [agents/research-to-code.md](agents/research-to-code.md) | The playbook for turning a public paper into a FoaMES change: sourcing rules, go or no-go triage, data mapping, invariant check, landing zones, test-first from the paper; [research-to-code-example.md](agents/research-to-code-example.md) is a worked run |
| [case-studies/README.md](case-studies/README.md) | Scaffolds for case studies of discrete, process and logistics improvements (changeover, yield and energy, electric trucks, autonomous trucks), with a shared template and honesty rules |
