Another Frappe app extends FoaMES by listing dotted paths under these hooks in its own `hooks.py`. No FoaMES file needs to change.

| Hook | Called with | Use it to |
| --- | --- | --- |
| `foames_erp_adapters` | (a list of class paths) | Register an ERP or system adapter ([Write an adapter](How-to-Write-an-adapter)) |
| `foames_machine_event_handlers` | `(machine_event_doc, machine_doc)` after each event is processed | Attach counts, states or alarms to your own records |
| `foames_machine_state_changed` | `(machine, previous_state, new_state, at)` on every state change | Mirror machine state somewhere else |
| `foames_machine_job_changed` | `(machine, previous_reference, at)` when Current Job Reference changes | Roll up the job that ended |
| `foames_floor_snapshot_extensions` | `(snapshot, since, now)`; mutate in place | Add a section to the floor snapshot that the page, rules and agents see |
| `foames_suggestion_rules` | `(snapshot) -> list[dict]` | Add rules. Each finding needs `rule_key`, `title`, `category`, `suggestion`, `severity`, and optionally `reference_doctype`, `reference_name`, `evidence` |
| `foames_process_event_extractors` | `(since, until)`, returns `Event` objects | Add your own records to process-mining event logs |

## Functions to call

| Function | Purpose |
| --- | --- |
| `foames.foames_kernel.doctype.external_reference.external_reference.get_reference(reference_type, external_id, erp_system=None, ignore_permissions=False)` | The External Reference for an ERP record, created if needed; safe under concurrency |
| `foames.foames_mes.api.record_events(events, source)`, `record_event(raw, source)` | Store raw events from inside the bench |
| `foames.foames_mes.doctype.machine.machine.get_machine_by_source(source_id)` | Machine name for a Source ID |
| `foames.foames_mes.doctype.agent_suggestion.agent_suggestion.raise_suggestions(findings, agent)` | Insert findings, skipping open duplicates and reopening resolved ones |
| `foames.foames_mes.oee.compute_oee(ledger, good, scrap, ideal_cycle_seconds)`, `ledger_from_states(intervals, planned_minutes)` | OEE arithmetic without a site |
| `foames.foames_process_mining.extractors.build_event_log(since, until, sources=None)` | An event log from every configured source |
| `foames.foames_process_mining.discovery.discover_dfg(log)`, `conformance.check_conformance(log, model)` | Process-mining analysis without a site |

## Building an app on FoaMES

List `foames` in your app's `required_apps`. Link freely to Machine, Machine Event, Downtime Record, OEE Period, Agent Suggestion and External Reference, but **never** to ERP DocTypes. See [AGENTS.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/AGENTS.md).
