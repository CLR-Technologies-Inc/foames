# Process mining in FoaMES

The FoaMES Process Mining module turns what the site records into event logs and runs the standard process-mining analyses over them. It answers the questions a Lean or Six Sigma engineer asks of real floor data: which paths do orders really take, how often, how long does each step take and wait, where does rework happen, and does the floor run the process the way it was defined.

Everything in the analysis core is plain Python with no Frappe dependency (`foames/foames_process_mining/eventlog.py`, `xes.py`, `ocel.py`, `discovery.py`, `conformance.py`), so it can be used in a notebook or another app. The DocTypes, extractors and API bind it to a site.

## The event log

| Term | Meaning in FoaMES |
| --- | --- |
| Case | The thing a trace follows: a work order, a lot, a machine-day, a downtime episode |
| Activity | What happened: an operation, a machine state, an inspection |
| Lifecycle | `start` or `complete` (the XES standard lifecycle), so an activity with a duration is two events |
| Resource | Who or what performed it: a machine, a workstation, an operator |
| Objects | Every entity the event touched, by type (`machine`, `lot`, `work_order`), for object-centric mining |

## Where events come from

| Source | How | Case |
| --- | --- | --- |
| Machine states (built in) | Every processed `State` and `Alarm` Machine Event | `<machine>:<date>` |
| Downtime (built in) | Every Downtime Record as a `Down` start/complete pair with its reason | the Downtime Record |
| Event Log Source | A field map over any DocType on the site: case, activity (or a fixed name), timestamp, optional end timestamp, resource, filters, attribute and object fields | the mapped field |
| Other apps | Dotted paths under the `foames_process_event_extractors` hook, called with `(since, until)` | whatever they return |

An Event Log Source names its DocType as text and resolves it at run time. This is how ERP records are mined without the core linking to them: when the DocType is not installed the source is skipped, so a site without ERPNext still installs and runs. A typical ERPNext mapping is:

| Field | Value |
| --- | --- |
| Source DocType | `Job Card` |
| Case Field | `work_order` |
| Activity Field | `operation` |
| Timestamp Field | `actual_start_date` |
| End Timestamp Field | `actual_end_date` |
| Resource Field | `workstation` |
| Filters | `{"docstatus": 1}` |
| Object Fields | `machine=workstation, item=production_item` |

Use **Preview events** on the form to check a mapping before relying on it.

## Saved logs

A **Process Event Log** is an extraction you keep: a window, the sources to use, and the events as JSON on the record. **Extract** builds it; **Analyse > Discover** shows the directly-follows graph, variants and a Graphviz DOT rendering; **Analyse > Check against another log** replays it on the graph discovered from a reference log (for example a golden week); **Export** attaches the log as an XES or OCEL 2.0 file for ProM, PM4Py, Celonis, Disco or any other tool.

## Analyses

| Analysis | Function | What it returns |
| --- | --- | --- |
| Discovery | `discovery.discover_dfg(log)` | Directly-follows graph with counts, start and end activities, and the time between each pair; `.filter(min_edge_count)` drops rare paths; `.to_dot()` draws it |
| Variants | `discovery.variant_table(log)` | Each distinct path with its share of cases and median duration |
| Performance | `discovery.throughput(log)`, `activity_durations(log)`, `bottlenecks(log)` | Case cycle time, service and waiting time per activity from start/complete pairs, the activities cases queue in front of |
| Rework | `discovery.rework(log)` | Activities repeated within a case |
| Conformance | `conformance.check_conformance(log, model)` | Per-trace replay with deviations classified as wrong start, unknown activity, disallowed transition or wrong end; fitness is the share of conforming moves |
| Footprints | `conformance.footprint(model)`, `compare_footprints(a, b)` | The Alpha relations (`->`, `<-`, `||`, `#`) and a cell-by-cell comparison of two models |

A reference model is a directly-follows graph. Build one with `conformance.model_from_sequence([...])` for a strict sequence, `conformance.model_from_log(golden_log)` from known-good runs, or `DirectlyFollowsGraph.from_dict(...)` from JSON another system supplies.

## API

All methods are under `foames.foames_process_mining.api` and take either `event_log` (a saved Process Event Log name) or `since`, `until` and `sources` to build a log on the fly. They need read permission on Process Event Log.

| Method | Purpose |
| --- | --- |
| `summary` | Counts and span of the log |
| `events` | The events as dicts |
| `discover` | DFG, variants, throughput, activity durations, bottlenecks and rework; `dot=1` adds the DOT text |
| `check_conformance` | `model` is a DFG dict, a JSON list of activities (strict sequence) or a saved log's name; returns the replay report and the footprint comparison |
| `export` | The log as XES XML or OCEL 2.0 JSON text (`fmt=xes` or `ocel`) |

An agent working through MCP calls these the same way it calls the floor API, and posts what it finds as an Agent Suggestion; see [agents/floor-agent.md](agents/floor-agent.md).

## Standards and prior art

XES follows IEEE 1849-2016 with the concept, time, lifecycle and organizational extensions. OCEL follows the OCEL 2.0 JSON specification. The directly-follows graph, footprint matrix and replay fitness follow the textbook definitions in van der Aalst, *Process Mining: Data Science in Action* (2016). No third-party process-mining library is required; logs export to all of them.
