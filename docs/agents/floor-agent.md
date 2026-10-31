# Agent playbook: reading the floor and raising suggestions

FoaMES exposes the plant floor to agents as one snapshot and takes suggestions back as records people act on. An agent needs a user with the FoaMES Engineer or FoaMES Operator role.

| Method | Purpose |
| --- | --- |
| `foames.foames_mes.api.get_floor_snapshot(days=1)` | Machines (state, last seen, counts of the last `days`, minutes since the last count, latest OEE), downtime by machine with the top reason, ERP references that resolved as Missing, open suggestions, and any section another app adds through the `foames_floor_snapshot_extensions` hook. |
| `foames.foames_mes.api.post_suggestion(title, category, suggestion, agent, severity, reference_doctype, reference_name, evidence, rule_key)` | Creates an Agent Suggestion. Pass a stable `rule_key` for a finding so repeats are not raised again while it is open. `evidence` is the numbers the suggestion rests on. |
| `foames.foames_mes.api.run_suggestion_rules(days=1)` | Runs the built-in rules now (silent or stalled machines, dominant downtime reason, missing ERP references) and any rule registered through the `foames_suggestion_rules` hook. The scheduler runs them hourly. |
| `foames.foames_mes.doctype.oee_period.oee_period.get_oee(machine, from_time, to_time, planned_minutes)` | OEE on demand with the time ledger and notes. |

Over MCP these are the tools `foames_get_floor_snapshot`, `foames_post_suggestion`, `foames_run_suggestion_rules` and `foames_get_oee`, next to `foames_list_machines`, `foames_get_machine`, `foames_list_downtime`, `foames_downtime_by_reason`, `foames_list_suggestions` and the `foames_mining_*` tools. Connecting a client and the full list are in [../mcp.md](../mcp.md).

Rules for an agent:

- Suggest, never act. Releases, holds, dispositions and ERP postings are done by people through the DocTypes; an agent's output is an Agent Suggestion with evidence.
- Quote the numbers from the snapshot in `evidence` so a person can check them.
- Categories: Yield, Downtime, Quality, Release, Machine Data, ERP, Other. Severity: Info, Warning, Critical.
- Unknown time (no machine signal) is loss, not production. Do not infer output from silence.
