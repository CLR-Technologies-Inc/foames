# The FoaMES MCP server

FoaMES speaks the Model Context Protocol (MCP), so an agent in Claude Desktop, Claude Code, Cursor or any other MCP client can read the plant floor and raise suggestions through tools, with no custom integration. The server exposes the public FoaMES API and nothing more: every tool is one whitelisted method that is already callable at `/api/method/...`, run as the user whose API key the agent holds, with that user's permissions.

The 23 tools cover machines and their state, machine events, downtime, OEE, the floor snapshot, Agent Suggestions, process mining (event logs, discovery, conformance, export) and ERP reference reads through the ERPNext and S/4HANA adapters. Two tools write, and both only create Agent Suggestions: agents suggest, people act.

## Two ways to connect

| Transport | Where it runs | For |
| --- | --- | --- |
| Streamable HTTP | Inside the site at `POST /api/method/foames.foames_mcp.api.mcp` | Clients that speak HTTP MCP and can send a header, such as Claude Code, and remote agents |
| stdio bridge | `python -m foames.foames_mcp` on the agent's machine, forwarding to that endpoint | Clients that start a local process, such as Claude Desktop and Cursor |

Both carry the same tools, because the bridge forwards every message to the site unchanged. The bridge is one file of standard-library Python (`foames/foames_mcp/bridge.py`), so it can be copied to any machine without installing FoaMES or Frappe there.

## Setting up

1. **Create a user for the agent** with the FoaMES role its job needs (see the permission table below), or use an existing one. Do not give an agent System Manager unless it has to read External References.
2. **Generate an API key and secret** on that User: User form, Settings tab, API Access, *Generate Keys*. Copy the secret; it is shown once.
3. **Connect the client.**

Claude Code, over HTTP:

```bash
claude mcp add --transport http foames https://mes.example.com/api/method/foames.foames_mcp.api.mcp \
  --header "Authorization: token <api_key>:<api_secret>"
```

Claude Desktop or any stdio client, through the bridge (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "foames": {
      "command": "python3",
      "args": ["/path/to/foames/foames/foames_mcp/bridge.py"],
      "env": {
        "FOAMES_URL": "https://mes.example.com",
        "FOAMES_API_KEY": "<api_key>",
        "FOAMES_API_SECRET": "<api_secret>"
      }
    }
  }
}
```

On a machine where the `foames` package is importable (the bench, or a `pip install -e apps/foames`), `python -m foames.foames_mcp` runs the same bridge. The bridge also takes `--url`, `--api-key` and `--api-secret` flags, and reads `FOAMES_TIMEOUT_SECONDS` (default 120), `FOAMES_CA_BUNDLE` (a PEM file when the site uses a private certificate authority) and `FOAMES_MCP_PATH` (when the endpoint is behind a path prefix).

A quick check from a shell, without any client:

```bash
curl -s https://mes.example.com/api/method/foames.foames_mcp.api.mcp \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool | head
```

## Authentication and permissions

Authentication is Frappe's own token authentication: `Authorization: token <api_key>:<api_secret>`. A desk session works too. Guests are refused by the framework before the server runs, and there is no OAuth flow, so a client that needs one (a hosted connector without header support) has to go through the bridge or a gateway that adds the header.

Permissions are the DocType permissions of the user behind the key, checked by the same `frappe.has_permission` calls the desk uses. Lists go through `frappe.get_list`, so user permissions (for example a user restricted to one Machine) apply as well. A tool the user may not run comes back as a tool result with `isError` and a "Not permitted" message, never as data.

| Tool | Needs |
| --- | --- |
| `foames_list_machines`, `foames_get_machine`, `foames_get_floor_snapshot` | read on Machine (Operator, Quality, Engineer) |
| `foames_list_machine_events` | read on Machine Event |
| `foames_list_downtime`, `foames_downtime_by_reason`, `foames_list_downtime_reasons` | read on Downtime Record / Downtime Reason |
| `foames_get_oee`, `foames_list_oee_periods` | read on OEE Period |
| `foames_list_suggestions`, `foames_get_suggestion` | read on Agent Suggestion |
| `foames_post_suggestion`, `foames_run_suggestion_rules` | create on Agent Suggestion (Operator, Engineer) |
| `foames_mining_*`, `foames_list_event_logs`, `foames_list_event_log_sources` | read on Process Event Log / Event Log Source |
| `foames_list_erp_systems` | any logged-in user |
| `foames_list_external_references`, `foames_lookup_erp_record` | read on External Reference (System Manager by default) |

`foames_get_machine` returns the sections the user may read and leaves the others out, so an Operator sees the machine and its downtime but not sections they lack the role for.

## The tools

| Tool | Returns |
| --- | --- |
| `foames_list_machines(status, machine_type, include_disabled, limit)` | Machines with state, last seen, last count, cycle time, shift |
| `foames_get_machine(machine)` | One machine, counts of the last 24 hours, open downtime, latest OEE Period, last 20 state changes |
| `foames_list_machine_events(machine, event_type, since, until, limit)` | Raw events, newest first, with counter deltas |
| `foames_list_downtime(machine, status, reason, since, until, limit)` | Downtime Records |
| `foames_downtime_by_reason(machine, since, until)` | Minutes per reason in the window, plus unclassified minutes |
| `foames_list_downtime_reasons()` | Reason codes, categories, planned flag |
| `foames_get_oee(machine, from_time, to_time, planned_minutes)` | OEE and the time ledger for any window, computed now |
| `foames_list_oee_periods(machine, since, until, limit)` | Saved daily OEE Periods |
| `foames_get_floor_snapshot(days)` | The whole floor as one object ([floor-view.md](floor-view.md#the-floor-snapshot)) |
| `foames_list_suggestions(status, category, severity, agent, limit)` | Agent Suggestions, open by default |
| `foames_get_suggestion(name)` | One suggestion with text, evidence, resolution |
| `foames_post_suggestion(title, category, suggestion, agent, severity, reference_doctype, reference_name, evidence, rule_key)` | Creates a suggestion; returns its name |
| `foames_run_suggestion_rules(days)` | Runs the rules now; returns the names created |
| `foames_mining_summary(event_log, since, until, sources)` | Event, case, variant and activity counts |
| `foames_mining_events(..., limit)` | The events |
| `foames_mining_discover(..., min_edge_count, dot)` | DFG, variants, throughput, durations, bottlenecks, rework |
| `foames_mining_conformance(model, ..., include_traces)` | Fitness, deviations, footprint comparison |
| `foames_mining_export(..., fmt)` | XES or OCEL 2.0 text |
| `foames_list_event_logs(status, limit)`, `foames_list_event_log_sources()` | Saved logs and configured sources |
| `foames_list_erp_systems()` | Registered adapters, availability, default system, reference types |
| `foames_list_external_references(erp_system, reference_type, status, limit)` | External References with resolution status |
| `foames_lookup_erp_record(reference_type, external_id, erp_system)` | One ERP record through its adapter; creates nothing |

Every tool carries its input schema and annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`) in `tools/list`, so a client can show which tools write. The server's `initialize` response includes the agent instructions from [agents/floor-agent.md](agents/floor-agent.md) in short form.

Datetimes are in the site's local time, `YYYY-MM-DD HH:MM:SS`; ISO 8601 strings are accepted as input.

## Behaviour and limits

- **Stateless.** The server issues no session id and keeps nothing between messages. Each POST carries one JSON-RPC message and returns one JSON response, or `202 Accepted` for a notification. JSON-RPC batches are not accepted (they left the MCP specification in revision 2025-06-18). A `GET` for the server-to-client stream is refused by the framework (the endpoint accepts POST only), which the specification allows for a server that does not push messages; clients treat it as non-fatal.
- **Protocol revisions** 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 are negotiated through `initialize`; a client that offers another revision gets 2025-11-25 back.
- **Errors.** A permission or validation failure in a tool is a tool result with `isError` and the message. Any other exception is logged in the site's Error Log and reported to the agent only by type, so nothing internal leaks. A failing tool's database writes are rolled back.
- **Writes commit** at the end of the request as for any Frappe API call. The two writing tools create Agent Suggestions only; `foames_post_suggestion` with a `rule_key` that is already open returns the open suggestion instead of creating a second one.
- **Throughput.** The bridge handles messages one at a time; a client that sends a `ping` during a long `foames_mining_discover` gets its answer after it. The HTTP endpoint runs under the site's normal workers.

## Extending the catalogue

The catalogue is `foames/foames_mcp/tools.py`: a list of `Tool(name, description, method, input_schema, read_only, ...)` records, each bound to a dotted path of a whitelisted method. Adding a tool is adding one record for a method that already exists and does its own permission check. A unit test holds every method to an allow-list of public API packages, so a tool cannot reach outside them by accident. Another app that wants its own tools should run its own MCP server rather than editing this list; `foames.foames_mcp.protocol.Server` is reusable for that.

## Tests

```bash
# protocol core, catalogue and bridge; no site needed (uses the mcp SDK end to end when installed)
python -m unittest foames.foames_mcp.test_mcp_protocol

# the endpoint on a site, with permissions
bench --site <site> run-tests --app foames --module foames.foames_mcp.test_mcp_api
```
