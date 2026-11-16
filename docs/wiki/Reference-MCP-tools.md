FoaMES is an MCP server. Each tool is one whitelisted method run as the user whose API key the agent holds. Three tools write: two create Agent Suggestions and one records a machine's current job. Nothing writes to an ERP.

| Transport | Endpoint |
| --- | --- |
| Streamable HTTP | `POST /api/method/foames.foames_mcp.api.mcp` with `Authorization: token <key>:<secret>` |
| stdio bridge | `python -m foames.foames_mcp` or `foames/foames_mcp/bridge.py`, configured by `FOAMES_URL`, `FOAMES_API_KEY`, `FOAMES_API_SECRET`, optional `FOAMES_TIMEOUT_SECONDS` (120), `FOAMES_CA_BUNDLE`, `FOAMES_MCP_PATH` |

## Tools

| Tool | Returns | Needs |
| --- | --- | --- |
| `foames_list_machines(status, machine_type, include_disabled, limit, ecl)` | Machines with state, last seen, last count, cycle time, shift, ECL | read on Machine |
| `foames_get_machine(machine)` | One machine, 24-hour counts, open downtime, latest OEE Period, last 20 state changes | read on Machine |
| `foames_get_floor_snapshot(days)` | The whole floor as one object; each machine carries its `ecl` | read on Machine |
| `foames_get_equipment_profile(machine, tier)` | A machine's ECL, minimum model tier (`oss`, `baseline`, `frontier`, or none at ECL 5), agent role, oversight (`none`, `single`, `team`), line ECL and unrated line members; with `tier`, an `eligibility` verdict and reason | read on Machine |
| `foames_list_equipment_complexity(line, include_disabled)` | Every machine's ECL, minimum tier and oversight, `by_level` counts, `unrated` machines, `lines` with each line's ECL | read on Machine |
| `foames_list_machine_events(machine, event_type, since, until, limit)` | Raw events with counter deltas | read on Machine Event |
| `foames_list_downtime(machine, status, reason, since, until, limit)` | Downtime Records | read on Downtime Record |
| `foames_downtime_by_reason(machine, since, until)` | Minutes per reason, plus unclassified | read on Downtime Record |
| `foames_list_downtime_reasons()` | Reasons, categories, planned flag | read on Downtime Reason |
| `foames_get_oee(machine, from_time, to_time, planned_minutes)` | OEE and the time ledger for any window | read on OEE Period |
| `foames_list_oee_periods(machine, since, until, limit)` | Saved OEE Periods | read on OEE Period |
| `foames_list_suggestions(status, category, severity, agent, limit)` | Agent Suggestions, open by default | read on Agent Suggestion |
| `foames_get_suggestion(name)` | One suggestion with evidence and resolution | read on Agent Suggestion |
| `foames_post_suggestion(title, category, suggestion, agent, severity, reference_doctype, reference_name, evidence, rule_key)` | **Writes.** Creates a suggestion; an open `rule_key` returns the existing one | create on Agent Suggestion |
| `foames_run_suggestion_rules(days)` | **Writes.** Runs the rules; returns names created | create on Agent Suggestion |
| `foames_set_current_job(machine, reference, at)` | **Writes.** Sets or ends a machine's current Job Card reference | write on Machine |
| `foames_mining_summary(event_log, since, until, sources)` | Event, case, variant and activity counts | read on Process Event Log |
| `foames_mining_events(..., limit)` | The events | read on Process Event Log |
| `foames_mining_discover(..., min_edge_count, dot)` | DFG, variants, throughput, durations, bottlenecks, rework | read on Process Event Log |
| `foames_mining_conformance(model, ..., include_traces)` | Fitness, deviations, footprint comparison | read on Process Event Log |
| `foames_mining_export(..., fmt)` | XES or OCEL 2.0 text | read on Process Event Log |
| `foames_list_event_logs(status, limit)` | Saved logs | read on Process Event Log |
| `foames_list_event_log_sources()` | Configured sources | read on Event Log Source |
| `foames_list_erp_systems()` | Registered adapters, availability, default, reference types | logged in |
| `foames_list_external_references(erp_system, reference_type, status, limit)` | External References with status | read on External Reference |
| `foames_lookup_erp_record(reference_type, external_id, erp_system)` | One ERP record through its adapter; creates nothing | read on External Reference |

## Behaviour

- Each tool carries `readOnlyHint`, `destructiveHint` and `idempotentHint` in `tools/list`.
- A refused tool returns a result with `isError` and "Not permitted", never data.
- Datetimes are site-local `YYYY-MM-DD HH:MM:SS`; ISO 8601 is accepted as input.
- The server is stateless, accepts one JSON-RPC message per POST (no batches) and negotiates protocol revisions 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25.
- Unexpected errors are logged in the site's Error Log and reported to the agent by type only. A failing tool's writes are rolled back.

Setup is in [Tutorial 3](Tutorial-3-Your-first-agent-over-MCP) and [docs/mcp.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/mcp.md).
