# AGENTS.md: working on and with FoaMES

This file is for coding agents and developers who implement something on top of FoaMES, connect a plant to it, or change it. It states what FoaMES is, the rules the code base keeps, where things are, how to extend it without forking it, and how to test. Human-facing guides are under [docs/](docs/README.md); the playbook for an agent that reads the floor at run time is [docs/agents/floor-agent.md](docs/agents/floor-agent.md).

## What FoaMES is

FoaMES is an ERP-agnostic manufacturing execution system built as a single Frappe app. It takes machine data in (signed webhook, MQTT, OPC UA, Sparkplug B), turns it into machine state, downtime, counter deltas and OEE, shows the floor on one page, and raises suggestions for people to act on. ERPs are reached only through adapters; ERPNext and SAP S/4HANA adapters ship in the app.

| Module | Package | Holds |
| --- | --- | --- |
| FoaMES Kernel | `foames/foames_kernel` | `External Reference`, `FoaMES Settings` |
| FoaMES MES | `foames/foames_mes` | Machine, Machine Event, Downtime Reason and Record, Machine Data Settings, OEE Period, Agent Suggestion, the Floor View page, the gateways, the API |
| FoaMES Adapters | `foames/foames_adapters` | The adapter contract, the ERPNext adapter, the S/4HANA adapter with its Settings, Outbox, Inbound IDoc and reconciliation report |

Frappe v15 and v16 are both supported; Python 3.10 or later. License: Apache-2.0, copyright CLR Technologies Inc. Contributions need the CLA described in [CONTRIBUTING.md](CONTRIBUTING.md).

## Invariants

Keep these whatever you build. A pull request that breaks one will not be merged.

1. **No Link field to an ERP DocType, anywhere.** A FoaMES record that needs an ERP record stores an `External Reference` (ERP system key, kernel reference type, external ID) and the adapter resolves it. Do not import from `erpnext`. The core must install and pass its tests on a plain Frappe site; CI checks this on v15 and v16 without ERPNext.
2. **Adapters are registered, not hard-wired.** New ERPs come through the `foames_erp_adapters` hook and subclass `foames.foames_adapters.base.ERPAdapter`. See [docs/erpnext-adapter.md](docs/erpnext-adapter.md#writing-an-adapter-for-another-erp).
3. **Counters never invent production.** Machines send running totals; FoaMES stores the delta against the previous reading of the same counter. A first reading, a reset, or an out-of-order reading yields zero; a wrap is counted only when the machine's Counter Rollover is known. The rules are in `foames/foames_mes/counters.py`.
4. **Unknown time is loss.** The OEE ledger is built from state events with Downtime Records overlaid, and an Unknown state is never run time. A machine that stops reporting gets an Unknown state event from the scheduler's staleness check (source System), and the Sparkplug gateway writes one at once on NDEATH or DDEATH. Do not add code that infers output or run time from the absence of events.
5. **Agents suggest; people act.** Anything an agent or a rule finds becomes an `Agent Suggestion` with evidence. FoaMES does not write tags, send commands to SCADA, change machine state on its own, or post to an ERP without an explicit, idempotent posting a person configured.
6. **Postings to an ERP are idempotent and sequenced.** The S/4HANA outbox is the model: an idempotency key per business event, a marker written into the created document, a check before resending after an unclear answer, exponential backoff, strict order within a sequence group. Follow it for any new write path.
7. **Pure logic stays pure.** `oee.py`, `counters.py`, `suggestions.py`, `signing.py`, `gateway/mapping.py`, `gateway/sparkplug.py` and `s4hana/outbox.py`, `odata.py`, `idoc.py`, `entities.py` import nothing from Frappe. Keep arithmetic, parsing and protocol code in such modules, and keep the Frappe DocType classes thin.
8. **Secrets live in Password fields** of a Settings DocType (`Machine Data Settings`, `S4HANA Settings`), read with `get_password`. Never in code, hooks or site config, never logged.
9. **Both Frappe versions.** Use `foames.tests_compat.IntegrationTestCase` for site tests. Avoid APIs that exist in only one of v15 and v16.

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
    oee.py  counters.py  suggestions.py  signing.py  kpi.py     pure logic (kpi.py: report roll-ups)
    tasks.py                  scheduler entry points
    gateway/                  mapping.py (normalise_event), mqtt.py, opcua.py, sparkplug.py
    doctype/                  Machine, Machine Event, Downtime Reason, Downtime Record,
                              Machine Data Settings (+ Machine Node Map), OEE Period, Agent Suggestion
    page/floor_view/          the Floor View page
    report/                   OEE Trend, Downtime Pareto, MTBF and MTTR, Suggestion Status, Process Throughput
    workspace/  number_card/  dashboard_chart/  foames_mes_dashboard/   role workspaces and dashboards
  foames_adapters/
    __init__.py               get_adapters, get_adapter, get_available_erp_systems
    base.py                   ERPAdapter, ResolvedReference, REFERENCE_TYPES, the error classes
    erpnext.py                ERPNextAdapter
    s4hana/                   adapter.py, entities.py, odata.py, outbox.py, idoc.py, api.py, fake.py
    doctype/                  S4HANA Settings (+ Entity Mapping), S4HANA Outbox, S4HANA Inbound IDoc
    report/                   S4HANA Outbox Reconciliation, ERP Outbox Health
    workspace/  number_card/  dashboard_chart/  foames_adapters_dashboard/   the Integration workspace
docs/                         human-facing guides; docs/agents/ holds run-time agent playbooks
cla/                          the Individual and Corporate CLAs
```

Files that only serve the design or build process of FoaMES (agent workspaces, worktrees, design notes) are not committed; `.gitignore` lists the paths. Agent files that help others adopt FoaMES, such as this one, are.

## Extension points

All of them are Frappe hooks: another app lists dotted paths in its own `hooks.py`, and FoaMES calls them. No FoaMES file needs to change.

| Hook | Called with | Use it to |
| --- | --- | --- |
| `foames_erp_adapters` | (list of class paths) | Register an ERP adapter |
| `foames_machine_event_handlers` | `(machine_event_doc, machine_doc)` after each event is processed | Attach counts, states or alarms to your own records |
| `foames_floor_snapshot_extensions` | `(snapshot: dict, since, now)`, mutate in place | Add a section to the floor snapshot, so the page, the rules and external agents see it |
| `foames_suggestion_rules` | `(snapshot: dict) -> list[dict]` | Add rules; each finding dict needs `rule_key`, `title`, `category`, `suggestion`, `severity`, optional `reference_doctype`, `reference_name`, `evidence` |
| `foames_s4hana_idoc_handlers` | dict of message type to handler list; handler gets `(inbound_doc, idoc, summary)` | Process an IDoc beyond recording its External Reference |

Code entry points you call rather than hook:

| Function | Purpose |
| --- | --- |
| `foames.foames_kernel.doctype.external_reference.external_reference.get_reference(reference_type, external_id, erp_system=None, ignore_permissions=False)` | Name of the External Reference for an ERP record, created if needed |
| `foames.foames_mes.api.record_events(events, source)` / `record_event(raw, source)` | Store raw events from inside the bench (gateways use this) |
| `foames.foames_mes.doctype.machine.machine.get_machine_by_source(source_id)` | Machine name for a gateway source id |
| `foames.foames_mes.doctype.agent_suggestion.agent_suggestion.raise_suggestions(findings, agent)` | Insert findings, skipping open duplicates and reopening resolved ones |
| `foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox.enqueue(operation, payload, idempotency_key, sequence_group=None, ...)` | Queue a posting to S/4HANA |
| `foames.foames_mes.oee.compute_oee(ledger, good, scrap, ideal_cycle_seconds)` and `ledger_from_states(intervals, planned_minutes)` | OEE arithmetic without a site |

## HTTP API surface

Whitelisted methods, called as `/api/method/<dotted path>`. Authentication is Frappe's: session cookie, or `Authorization: token <api_key>:<api_secret>`.

| Method | Verb | Permission | Purpose |
| --- | --- | --- | --- |
| `foames.foames_mes.api.ingest_machine_events` | POST | HMAC signature with the webhook secret, or a user with FoaMES Operator, Engineer or System Manager | Record machine events; body `{"events": [...]}` or one event |
| `foames.foames_mes.api.get_floor_snapshot` | GET | read on Machine | The whole floor as one dict (`days` parameter) |
| `foames.foames_mes.api.run_suggestion_rules` | POST | create on Agent Suggestion | Run the rules now; returns the names created |
| `foames.foames_mes.api.post_suggestion` | POST | create on Agent Suggestion | An external agent posts one suggestion |
| `foames.foames_mes.doctype.oee_period.oee_period.get_oee` | GET | read on OEE Period | OEE for any window without saving a period |
| `foames.foames_adapters.get_available_erp_systems` | GET | logged in | Registered adapters and their availability |
| `foames.foames_adapters.s4hana.api.receive_idoc` | POST | create on S4HANA Inbound IDoc (FoaMES Integration role) | S/4HANA's XML HTTP port posts IDocs here |

Document methods callable with `frm.call` or `run_doc_method`: `External Reference.resolve`, `S4HANA Settings.test_connection`, `S4HANA Outbox.requeue`, `S4HANA Outbox.cancel_posting`.

The event shape, state aliases and signing scheme are in [docs/machine-data.md](docs/machine-data.md). For an MCP server, wrap `get_floor_snapshot`, `post_suggestion` and `get_oee`; suggested tool names are in [docs/agents/floor-agent.md](docs/agents/floor-agent.md).

## Common tasks

**Connect a new kind of machine or gateway.** Prefer the signed webhook; it needs nothing installed on the bench. Send running totals for counters, not increments, with the machine's Source ID in `machine` and the source's own event id in `id` so retries deduplicate. If the source speaks MQTT, publish JSON to `<prefix>/<source id>/<event type>`. If it is Ignition, read [docs/ignition.md](docs/ignition.md). Do not add a new gateway module for a protocol a bridge can translate to the webhook.

**Build an app on FoaMES.** Depend on `foames` in your app's `required_apps`. Link to `Machine`, `Machine Event`, `Downtime Record`, `OEE Period`, `Agent Suggestion` and `External Reference` freely; never to ERP DocTypes. Use `foames_machine_event_handlers` to react to events, `foames_floor_snapshot_extensions` to show your data on the floor, and `foames_suggestion_rules` to raise findings from it.

**Add a reference type to an adapter.** For ERPNext, add a row to `ERPNEXT_DOCTYPES` in `erpnext.py` (kernel type, DocType, label field). For S/4HANA, map it in S4HANA Settings at run time, or add a default `EntitySpec` to `s4hana/entities.py` with its service, entity set, key fields and label. Adding a *new* kernel reference type means extending `REFERENCE_TYPES` in `base.py` and the Select options on External Reference and S4HANA Entity Mapping together.

**Change OEE or the rules.** Edit the pure module and its unit test first (`test_oee_and_rules.py`), then the DocType or task that calls it. Keep the time ledger exhaustive: every planned minute lands in exactly one bucket, and the gap goes to unknown.

**Add a scheduled job.** Register it in `scheduler_events` in `hooks.py` and make it idempotent, as `compute_daily_oee` is (it skips a period that already exists).

**Add cryptography, a secret or a connected service.** Update `sbom/curated.json` in the same pull request: it feeds the cryptography bill of materials and the `services` list of the published CycloneDX SBOM, which the dependency scan cannot see. See [docs/sbom.md](docs/sbom.md#keeping-it-true).

## Testing

```bash
# pure-logic tests, no site needed
python -m unittest foames.foames_mes.test_oee_and_rules foames.foames_mes.test_machine_data_logic foames.foames_mes.test_sparkplug foames.foames_mes.test_kpi

# everything, on a bench
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app foames
bench --site <site> run-tests --app foames --module foames.foames_mes.doctype.oee_period.test_oee_period
```

Without a bench on the machine, `cd docker && ./bench.sh up && ./bench.sh test` runs the suite in Docker on Frappe v15 or v16, with or without ERPNext; see [docs/dev-bench.md](docs/dev-bench.md).

The S/4HANA tests use `foames/foames_adapters/s4hana/fake.py`, an in-memory stand-in for the OData transport, so no SAP system is needed; they run under `bench run-tests` because the adapters package imports Frappe. CI runs the suite on Frappe v15, v16, and v16 with ERPNext, plus Frappe's semgrep rules and pip-audit. The SBOM workflow runs `python -m unittest discover -s sbom` and builds and validates the CycloneDX 1.7 SBOM on each Frappe line.

## Conventions

- Formatting and linting through `pre-commit` (ruff with tabs and a 110-column line, eslint, prettier). Run `pre-commit install` once in `apps/foames`.
- Strings shown to users go through `frappe._`.
- A DocType's Python file holds the document class and the module-level functions that operate on it; the arithmetic it needs lives in a pure module next to it.
- Commit messages say what changed and why. Credit third-party code and ship its license notice with it.
- Do not add SAP code, SAP API metadata or any vendor SDK to the repository; the S/4HANA adapter talks to released OData APIs and IDoc XML only, and the entity defaults are documented as things to check against a system's `$metadata`.
