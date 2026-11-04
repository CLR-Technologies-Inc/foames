# AGENTS.md: working on and with FoaMES

This file is for coding agents and developers who implement something on top of FoaMES, connect a plant to it, or change it. It states what FoaMES is, the rules the code base keeps, where things are, how to extend it without forking it, and how to test. Human-facing guides are under [docs/](docs/README.md); the playbook for an agent that reads the floor at run time is [docs/agents/floor-agent.md](docs/agents/floor-agent.md).

**This file is vendor-neutral on purpose.** Anything that is true of one ERP, SCADA product or other vendor (its settings, its rules, its hooks and endpoints, how to test it) lives in that vendor's own `AGENTS.md`, next to its code, and in its guide under `docs/vendors/`. Read the `AGENTS.md` closest to the code you change; see [Finding vendor guidance](#finding-vendor-guidance).

## What FoaMES is

FoaMES is an ERP-agnostic manufacturing execution system built as a single Frappe app. It takes machine data in (signed webhook, MQTT, OPC UA, Sparkplug B), turns it into machine state, downtime, counter deltas and OEE, shows the floor on one page, and raises suggestions for people to act on. ERPs are reached only through adapters, registered by hook; some ship in the app and other apps can add more.

| Module | Package | Holds |
| --- | --- | --- |
| FoaMES Kernel | `foames/foames_kernel` | `External Reference`, `FoaMES Settings` |
| FoaMES MES | `foames/foames_mes` | Machine, Machine Event, Downtime Reason and Record, Machine Data Settings, Shift Pattern, OEE Period, Agent Suggestion, Andon Call and Call Type, Maintenance Plan and Work Order, the Floor View page, the gateways, the API |
| FoaMES Adapters | `foames/foames_adapters` | The adapter contract and registry, one subpackage per vendor (each with its own `AGENTS.md`), the shared Integration workspace |
| FoaMES Process Mining | `foames/foames_process_mining` | Event Log Source, Process Event Log, the event extractors, the XES and OCEL exports, discovery and conformance analysis, and their API |
| MCP server | `foames/foames_mcp` | The MCP tool catalogue, the Streamable HTTP endpoint, the stdio bridge, read methods for agents |

Frappe v15 and v16 are both supported; Python 3.10 or later. License: Apache-2.0, copyright CLR Technologies Inc. Contributions need the CLA described in [CONTRIBUTING.md](CONTRIBUTING.md).

## Invariants

Keep these whatever you build. A pull request that breaks one will not be merged.

1. **No Link field to an ERP DocType, anywhere.** A FoaMES record that needs an ERP record stores an `External Reference` (ERP system key, kernel reference type, external ID) and the adapter resolves it. Do not import an ERP's package. The core must install and pass its tests on a plain Frappe site; CI checks this on v15 and v16 without any ERP.
2. **Adapters are registered, not hard-wired.** New ERPs come through the `foames_erp_adapters` hook and subclass `foames.foames_adapters.base.ERPAdapter`. See [docs/adapters.md](docs/adapters.md#writing-an-adapter-for-another-erp) and [foames/foames_adapters/AGENTS.md](foames/foames_adapters/AGENTS.md).
3. **Counters never invent production.** Machines send running totals; FoaMES stores the delta against the previous reading of the same counter. A first reading, a reset, or an out-of-order reading yields zero; a wrap is counted only when the machine's Counter Rollover is known. The rules are in `foames/foames_mes/counters.py`.
4. **Unknown time is loss.** The OEE ledger is built from state events with Downtime Records overlaid, and an Unknown state is never run time. A machine that stops reporting gets an Unknown state event from the scheduler's staleness check (source System), and the Sparkplug gateway writes one at once on NDEATH or DDEATH. Do not add code that infers output or run time from the absence of events.
5. **Agents suggest; people act.** Anything an agent or a rule finds becomes an `Agent Suggestion` with evidence. FoaMES does not write tags, send commands to SCADA, change machine state on its own, or post to an ERP without an explicit, idempotent posting a person configured.
6. **Postings to an ERP are idempotent and sequenced.** An idempotency key per business event, a marker written into the created document, a check before resending after an unclear answer, exponential backoff, strict order within a sequence group. The adapters' outboxes are the model; the details are in [foames/foames_adapters/AGENTS.md](foames/foames_adapters/AGENTS.md). Follow it for any new write path.
7. **Pure logic stays pure.** `oee.py`, `counters.py`, `shifts.py`, `andon.py`, `suggestions.py`, `maintenance.py`, `signing.py`, `gateway/mapping.py`, `gateway/sparkplug.py`, the process-mining core and `foames_mcp/protocol.py`, `tools.py`, `bridge.py` import nothing from Frappe, and so do the arithmetic, parsing and protocol modules of each adapter (each vendor's `AGENTS.md` lists its own). Keep arithmetic, parsing and protocol code in such modules, and keep the Frappe DocType classes thin.
8. **Secrets live in Password fields** of a Settings DocType (`Machine Data Settings`, or the adapter's own Settings), read with `get_password`. Never in code, hooks or site config, never logged.
9. **Both Frappe versions.** Use `foames.tests_compat.IntegrationTestCase` for site tests. Avoid APIs that exist in only one of v15 and v16.

## Finding vendor guidance

Vendors are open-ended: a site may have none, one or twenty adapters, bundled or added by other apps. Do not take the list from a document; discover it, then read the guidance that sits next to the code.

1. **Read the nearest `AGENTS.md`.** Before you change a directory, look for an `AGENTS.md` in it and in its parents up to this one; the closest one wins where they differ. `foames/foames_adapters/AGENTS.md` covers every adapter, and each vendor subpackage under it has its own.
2. **Find what is installed.** `ls foames/foames_adapters/`; `frappe.get_hooks("foames_erp_adapters")` for the registered adapter classes; the whitelisted `foames.foames_adapters.get_available_erp_systems` for each adapter's key, label and whether its ERP is reachable on the site. For a running installation, map from those answers to the vendor guidance, not the other way round.
3. **Human guides** for a vendor are under [docs/vendors/](docs/vendors/README.md), one folder per vendor. Vendor-neutral material (External References, running without an ERP, writing an adapter) is in [docs/adapters.md](docs/adapters.md).
4. **When you add a vendor**, add its `AGENTS.md` and guide with it, and do not edit this file; see "Adding a vendor" in [foames/foames_adapters/AGENTS.md](foames/foames_adapters/AGENTS.md).

## Repository map

```
foames/
  hooks.py                    app hooks: adapters, scheduler events, extension hook names
  install.py                  creates the six FoaMES roles before DocTypes are synced
  tests_compat.py             IntegrationTestCase that works on v15 and v16
  foames_kernel/doctype/      External Reference (get_reference, make_reference_key), FoaMES Settings
  foames_mes/
    api.py                    ingest_machine_events, get_floor_snapshot, run_suggestion_rules, post_suggestion
    floor.py                  floor_snapshot, collect_findings
    oee.py  counters.py  shifts.py  suggestions.py  signing.py  kpi.py  spc.py  maintenance.py   pure logic (kpi.py: report roll-ups, shifts.py: shift calendars, spc.py: control charts)
    spc_monitor.py            SPC over Measurement events: settings, findings, get_control_chart
    tasks.py                  scheduler entry points
    gateway/                  mapping.py (normalise_event), mqtt.py, opcua.py, sparkplug.py
    doctype/                  Machine, Machine Event, Downtime Reason, Downtime Record,
                              Machine Data Settings (+ Machine Node Map), Shift Pattern (+ shifts, non-working days),
                              OEE Period, Agent Suggestion, Andon Call, Andon Call Type,
                              Maintenance Plan, Maintenance Work Order
    page/floor_view/          the Floor View page
    report/                   OEE Trend, Downtime Pareto, MTBF and MTTR, Suggestion Status, Process Throughput, SPC Control Chart,
                              Maintenance Due List
    workspace/  number_card/  dashboard_chart/  foames_mes_dashboard/   role workspaces and dashboards
  foames_adapters/
    AGENTS.md                 the adapter layer: contract, rules every adapter keeps, how to add a vendor
    __init__.py               get_adapters, get_adapter, get_available_erp_systems
    base.py                   ERPAdapter, ResolvedReference, REFERENCE_TYPES, the error classes
    machine_window.py         a machine's counter totals and states in a window, for the roll-ups
    <vendor>/                 one subpackage per vendor adapter, each with its own AGENTS.md
    doctype/  report/         the adapters' Settings and Outbox DocTypes and shared reports
    workspace/  number_card/  dashboard_chart/  foames_adapters_dashboard/   the Integration workspace
  foames_process_mining/
    eventlog.py  xes.py  ocel.py  discovery.py  conformance.py   pure logic: the event log, the XES and
                              OCEL 2.0 formats, directly-follows discovery and performance, conformance
    extractors.py             build_event_log, the built-in machine-state and downtime extractors, field maps
    api.py                    summary, events, discover, check_conformance, export
    doctype/                  Event Log Source, Process Event Log (+ Process Event Log Source)
  foames_mcp/
    protocol.py               MCP/JSON-RPC server core (pure), tools.py the catalogue (pure)
    api.py                    the Streamable HTTP endpoint; reads.py whitelisted read methods
    bridge.py                 stdio bridge for desktop agents, standard library only
docs/                         human-facing guides; docs/agents/ holds run-time agent playbooks
cla/                          the Individual and Corporate CLAs
```

Files that only serve the design or build process of FoaMES (agent workspaces, worktrees, design notes) are not committed; `.gitignore` lists the paths. Agent files that help others adopt FoaMES, such as this one, are.

## Extension points

All of them are Frappe hooks: another app lists dotted paths in its own `hooks.py`, and FoaMES calls them. No FoaMES file needs to change. These are the core hooks; a vendor adapter that declares hooks of its own documents them in its own `AGENTS.md`.

| Hook | Called with | Use it to |
| --- | --- | --- |
| `foames_erp_adapters` | (list of class paths) | Register an ERP adapter |
| `foames_machine_event_handlers` | `(machine_event_doc, machine_doc)` after each event is processed | Attach counts, states or alarms to your own records |
| `foames_floor_snapshot_extensions` | `(snapshot: dict, since, now)`, mutate in place | Add a section to the floor snapshot, so the page, the rules and external agents see it |
| `foames_suggestion_rules` | `(snapshot: dict) -> list[dict]` | Add rules; each finding dict needs `rule_key`, `title`, `category`, `suggestion`, `severity`, optional `reference_doctype`, `reference_name`, `evidence` |
| `foames_process_event_extractors` | `(since, until)`, returns an iterable of `foames.foames_process_mining.eventlog.Event` | Add your own records to the process-mining event log |

Code entry points you call rather than hook:

| Function | Purpose |
| --- | --- |
| `foames.foames_kernel.doctype.external_reference.external_reference.get_reference(reference_type, external_id, erp_system=None, ignore_permissions=False)` | Name of the External Reference for an ERP record, created if needed |
| `foames.foames_mes.api.record_events(events, source)` / `record_event(raw, source)` | Store raw events from inside the bench (gateways use this) |
| `foames.foames_mes.doctype.machine.machine.get_machine_by_source(source_id)` | Machine name for a gateway source id |
| `foames.foames_mes.doctype.agent_suggestion.agent_suggestion.raise_suggestions(findings, agent)` | Insert findings, skipping open duplicates and reopening resolved ones |
| `foames.foames_mes.oee.compute_oee(ledger, good, scrap, ideal_cycle_seconds)` and `ledger_from_states(intervals, planned_minutes)` | OEE arithmetic without a site |
| `foames.foames_process_mining.extractors.build_event_log(since, until, sources=None)` | An `EventLog` from the built-in extractors, the enabled Event Log Sources and the hook extractors |
| `foames.foames_process_mining.discovery.discover_dfg(log)` and `conformance.check_conformance(log, model)` | Process-mining analysis without a site |

## HTTP API surface

Whitelisted methods, called as `/api/method/<dotted path>`. Authentication is Frappe's: session cookie, or `Authorization: token <api_key>:<api_secret>`. These are the core methods. Each vendor adapter's endpoints, with their permissions, are in its own `AGENTS.md`.

| Method | Verb | Permission | Purpose |
| --- | --- | --- | --- |
| `foames.foames_mes.api.ingest_machine_events` | POST | HMAC signature with the webhook secret, or a user with FoaMES Operator, Engineer or System Manager | Record machine events; body `{"events": [...]}` or one event |
| `foames.foames_mes.api.get_floor_snapshot` | GET | read on Machine | The whole floor as one dict (`days` parameter) |
| `foames.foames_mes.api.run_suggestion_rules` | POST | create on Agent Suggestion | Run the rules now; returns the names created |
| `foames.foames_mes.api.post_suggestion` | POST | create on Agent Suggestion | An external agent posts one suggestion |
| `foames.foames_mes.spc_monitor.get_control_chart` | GET | read on Machine Event | I-MR or X-bar R chart of one machine measurement with run-rule signals |
| `foames.foames_mes.doctype.oee_period.oee_period.get_oee` | GET | read on OEE Period | OEE for any window without saving a period |
| `foames.foames_mes.doctype.andon_call.andon_call.raise_andon` | POST | create on Andon Call | Raise a call for help at a machine (`machine`, `call_type`, `note`) |
| `foames.foames_mes.doctype.andon_call.andon_call.acknowledge_andon` / `resolve_andon` | POST | write on Andon Call | Acknowledge, resolve or cancel a call |
| `foames.foames_mes.doctype.andon_call.andon_call.list_open_andon_calls` | GET | read on Andon Call | Open and acknowledged calls with minutes open and targets |
| `foames.foames_adapters.get_available_erp_systems` | GET | logged in | Registered adapters and their availability |
| `foames.foames_process_mining.api.summary`, `events`, `discover`, `check_conformance`, `export` | GET or POST | read on Process Event Log | Process mining over a saved `event_log` or a log built from `since`, `until` and `sources`; `discover` takes `dot=1`, `check_conformance` takes `model`, `export` takes `fmt=xes` or `ocel` |
| `foames.foames_mcp.reads.*` | GET | read on the DocType listed | Agent-friendly reads: machines, events, downtime, OEE periods, suggestions, ERP systems and references, event logs |
| `foames.foames_mcp.api.mcp` | POST | logged in; each tool checks its own | The MCP endpoint (Streamable HTTP) |

Document methods callable with `frm.call` or `run_doc_method`: `External Reference.resolve`, `Event Log Source.preview`, `Process Event Log.extract`, `discover`, `check_against`, `export_file`.

The event shape, state aliases and signing scheme are in [docs/machine-data.md](docs/machine-data.md); the event log, its sources and the analyses are in [docs/process-mining.md](docs/process-mining.md).

**MCP.** The same surface is available to agents as MCP tools: `POST /api/method/foames.foames_mcp.api.mcp` is a Streamable HTTP MCP server authenticated with the API key, and `python -m foames.foames_mcp` is a stdio bridge to it for desktop clients. The catalogue is `foames/foames_mcp/tools.py`; each tool is one whitelisted method above, run as the key's user. Setup and the tool list are in [docs/mcp.md](docs/mcp.md). To expose a new whitelisted method to agents, add a `Tool` record there; the method keeps its own permission check.

## Common tasks

**Connect a new kind of machine or gateway.** Prefer the signed webhook; it needs nothing installed on the bench. Send running totals for counters, not increments, with the machine's Source ID in `machine` and the source's own event id in `id` so retries deduplicate. If the source speaks MQTT, publish JSON to `<prefix>/<source id>/<event type>`. If the source belongs to a product with a guide under [docs/vendors/](docs/vendors/README.md), read it first. Do not add a new gateway module for a protocol a bridge can translate to the webhook.

**Build an app on FoaMES.** Depend on `foames` in your app's `required_apps`. Link to `Machine`, `Machine Event`, `Downtime Record`, `OEE Period`, `Agent Suggestion` and `External Reference` freely; never to ERP DocTypes. Use `foames_machine_event_handlers` to react to events, `foames_floor_snapshot_extensions` to show your data on the floor, and `foames_suggestion_rules` to raise findings from it.

**Add a reference type to an adapter, or an adapter for a new ERP.** Read [foames/foames_adapters/AGENTS.md](foames/foames_adapters/AGENTS.md), then the `AGENTS.md` of the vendor package you change; each says how its own mapping is extended. Adding a *new* kernel reference type means extending `REFERENCE_TYPES` in `base.py` and the Select options on External Reference and on the adapters' mapping DocTypes together.

**Turn a published method into a change.** Follow [docs/agents/research-to-code.md](docs/agents/research-to-code.md): triage the paper against the invariants before reading it in depth, map its inputs to what FoaMES records, pick one landing zone, and write the test from the paper's own example first. Most papers end as a no-go with one metric or loss category carried over.

**Change OEE or the rules.** Edit the pure module and its unit test first (`test_oee_and_rules.py`), then the DocType or task that calls it. Keep the time ledger exhaustive: every planned minute lands in exactly one bucket, and the gap goes to unknown.

**Mine records from another DocType or app.** For a DocType on the site, create an Event Log Source with a field map (case, activity, timestamp, optional end timestamp, resource, filters, object fields) and check it with **Preview events**; the DocType is named as text and the source is skipped when it is not installed. For records your app builds itself, register a `foames_process_event_extractors` hook that yields `Event` objects. New analyses go in the pure modules with a test in `test_process_mining_logic.py`, and are exposed through `api.py` or a Process Event Log method.

**Add a scheduled job.** Register it in `scheduler_events` in `hooks.py` and make it idempotent, as `compute_daily_oee` is (it skips a period that already exists).

**Add cryptography, a secret or a connected service.** Update `sbom/curated.json` in the same pull request: it feeds the cryptography bill of materials and the `services` list of the published CycloneDX SBOM, which the dependency scan cannot see. See [docs/sbom.md](docs/sbom.md#keeping-it-true).

## Testing

```bash
# pure-logic tests, no site needed
python -m unittest foames.foames_mes.test_oee_and_rules foames.foames_mes.test_machine_data_logic foames.foames_mes.test_sparkplug foames.foames_mes.test_kpi
python -m unittest foames.foames_process_mining.test_process_mining_logic foames.foames_mcp.test_mcp_protocol

# everything, on a bench
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app foames
bench --site <site> run-tests --app foames --module foames.foames_mes.doctype.oee_period.test_oee_period
```

Without a bench on the machine, `cd docker && ./bench.sh up && ./bench.sh test` runs the suite in Docker on Frappe v15 or v16, with or without an optional ERP app; see [docs/dev-bench.md](docs/dev-bench.md).

Adapter tests never need a vendor's production system: a remote system is tested against an in-memory stand-in for its transport, and tests that need an ERP installed on the site skip when it is not. How to run a vendor's tests, and what they need, is in that vendor's `AGENTS.md`. CI runs the suite on Frappe v15, v16, and v16 with an ERP app installed, plus Frappe's semgrep rules and pip-audit. The SBOM workflow runs `python -m unittest discover -s sbom` and builds and validates the CycloneDX 1.7 SBOM on each Frappe line.

## Conventions

- Formatting and linting through `pre-commit` (ruff with tabs and a 110-column line, eslint, prettier). Run `pre-commit install` once in `apps/foames`.
- Strings shown to users go through `frappe._`.
- A DocType's Python file holds the document class and the module-level functions that operate on it; the arithmetic it needs lives in a pure module next to it.
- Commit messages say what changed and why. Credit third-party code and ship its license notice with it.
- Do not add a vendor's proprietary code, API metadata or SDK to the repository. Each adapter talks to the vendor's published interfaces only; what that means for a particular vendor is in its `AGENTS.md`.
- Keep vendor facts out of this file, `README.md` and the vendor-neutral pages in `docs/`. They belong in the vendor's `AGENTS.md` and its folder under `docs/vendors/`.
