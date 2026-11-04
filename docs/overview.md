# What FoaMES records

The records, pages and analyses FoaMES adds to a Frappe site, by area. Each section links to the guide that explains it in depth. For the code layout and the rules the code keeps, see [../AGENTS.md](../AGENTS.md).

## Machine data

| Record | Module | Role |
| --- | --- | --- |
| Machine | MES | A machine that reports events, with its state, last-seen time, counter rollover and OEE parameters. |
| Machine Event | MES | One event from a machine (state, count, measurement, alarm, message), processed into state, downtime and counter deltas. |
| Downtime Reason, Downtime Record | MES | Downtime opened and closed automatically from machine state, with a reason an operator assigns. |
| Machine Data Settings | MES | Webhook secret, MQTT broker, Sparkplug B group, OPC UA endpoint, security mode and certificates, the node and metric map, staleness threshold. |

Events arrive through a signed webhook, an MQTT gateway, a Sparkplug B gateway or an OPC UA gateway. SCADA products connect through whichever of these paths they support, or through a script that posts to the webhook; vendor guides are under [docs/vendors/](vendors/README.md). Counter readings become deltas, and a first, reset or out-of-order reading never invents production. See [docs/machine-data.md](machine-data.md), including the hook other apps use to act on processed events.

## OEE, the floor view and agent suggestions

| Record or page | Module | Role |
| --- | --- | --- |
| OEE Period | MES | OEE for a machine over a period from its events, downtime and counts. Planned downtime is excluded from availability; time without a machine signal is counted as loss, never as run time. One period per machine per day is computed by the scheduler over the machine's scheduled window, or one per shift when the machine has a Shift Pattern. |
| Shift Pattern | MES | A shift calendar machines share: shifts with start, length and weekdays, plus non-working days. Drives the daily OEE periods, the operating time in MTBF and the shift shown on the floor. |
| Floor View (page) | MES | Live tiles per machine with state, counts and OEE, plus open suggestions. |
| Agent Suggestion | MES | A finding raised by the built-in rules or by an external agent, with evidence, for a person to accept or dismiss. |
| Andon Call, Andon Call Type | MES | A call for help at a machine (maintenance, material, quality, supervisor, safety), with response and resolution times. A call that misses its type's targets becomes an Agent Suggestion. |
| SPC Control Chart (report) | MES | I-MR or X-bar R chart of a machine measurement with Nelson or Western Electric run rules; signals on recent readings become Quality suggestions. |

The OEE arithmetic and the suggestion rules have no Frappe dependency (`foames/foames_mes/oee.py`, `suggestions.py`, `spc.py`). The counter-delta, owed-count and coverage ideas follow public MES practice, including the FactorySemantics MES design notes. See [docs/agents/floor-agent.md](agents/floor-agent.md) for the agent API and the hooks that add snapshot sections and rules.

## Process mining

| Record | Module | Role |
| --- | --- | --- |
| Event Log Source | Process Mining | A field map that turns any DocType's records into events (case, activity, timestamps, resource, objects). ERP records are named as text and skipped when not installed. |
| Process Event Log | Process Mining | A saved extraction over a window and chosen sources, with discovery, conformance against another log, and XES or OCEL 2.0 export from the form. |

Machine states and downtime are built-in sources. The analyses (directly-follows graph, variants, throughput, waiting times, rework, conformance replay and footprint comparison) have no Frappe dependency (`foames/foames_process_mining/discovery.py`, `conformance.py`). See [docs/process-mining.md](process-mining.md).

## Agents and MCP

FoaMES is an MCP server. `POST /api/method/foames.foames_mcp.api.mcp` speaks the Model Context Protocol over Streamable HTTP with a Frappe API key, and `python -m foames.foames_mcp` is a standard-library stdio bridge to it for Claude Desktop, Claude Code, Cursor and other clients. The 24 tools read machines and state, downtime, OEE, the floor snapshot, suggestions, process mining and ERP references through the adapters, each with the permissions of the key's user; the only writes create Agent Suggestions or record a machine's current job. See [docs/mcp.md](mcp.md).
