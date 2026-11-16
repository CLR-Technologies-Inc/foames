Whitelisted methods are called as `/api/method/<dotted path>`. Authentication is Frappe's: a session cookie, or `Authorization: token <api_key>:<api_secret>`. Each method checks the caller's permissions. Vendor adapters' own endpoints are listed in each adapter's `AGENTS.md` and vendor guide.

## Core methods

| Method | Verb | Permission | Purpose |
| --- | --- | --- | --- |
| `foames.foames_mes.api.ingest_machine_events` | POST | HMAC signature, or Operator, Engineer or System Manager | Record machine events ([format](Reference-Machine-event-format)) |
| `foames.foames_mes.api.get_floor_snapshot` | GET | read on Machine | The whole floor as one object (`days`, default 1) |
| `foames.foames_mes.api.run_suggestion_rules` | POST | create on Agent Suggestion | Run the rules now; returns the names created |
| `foames.foames_mes.api.post_suggestion` | POST | create on Agent Suggestion | An external agent posts one suggestion |
| `foames.foames_mes.api.set_current_job` | POST | write on Machine | Set (`machine`, `reference`, `at`) or end (no `reference`) a machine's current job |
| `foames.foames_mes.doctype.oee_period.oee_period.get_oee` | GET | read on OEE Period | OEE for any window without saving (`machine`, `from_time`, `to_time`, `planned_minutes`) |
| `foames.foames_mes.spc_monitor.get_control_chart` | GET | read on Machine Event | I-MR or X-bar R chart of one measurement with run-rule signals |
| `foames.foames_mes.doctype.andon_call.andon_call.raise_andon` | POST | create on Andon Call | `machine`, `call_type`, optional `note` |
| `foames.foames_mes.doctype.andon_call.andon_call.acknowledge_andon` | POST | write on Andon Call | `name` |
| `foames.foames_mes.doctype.andon_call.andon_call.resolve_andon` | POST | write on Andon Call | `name`, optional `resolution`, `cancel` |
| `foames.foames_mes.doctype.andon_call.andon_call.list_open_andon_calls` | GET | read on Andon Call | Open and acknowledged calls, oldest first |
| `foames.foames_mes.doctype.maintenance_plan.maintenance_plan.make_work_order` | POST | create on Maintenance Work Order | Open a work order for a plan, or return the open one |
| `foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure.get_effective_sops` | GET | read on SOP | Effective SOPs, optionally at a machine |
| `foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure.operator_sop_gaps` | GET | read; Quality, Supervisor or Engineer for another user | SOPs a user must still acknowledge |
| `foames.foames_mes.site_cbom.get_site_cbom` | GET | System Manager | The site's CycloneDX CBOM with deployed OPC UA certificates |
| `foames.foames_adapters.get_available_erp_systems` | GET | logged in | Registered adapters and whether each is reachable |
| `foames.foames_process_mining.api.summary`, `events`, `discover`, `check_conformance`, `export` | GET or POST | read on Process Event Log | Process mining over `event_log` or `since`, `until`, `sources` |
| `foames.foames_bms.api.ingest_point_readings` | POST | HMAC signature, or Operator, Engineer or System Manager | Record building point readings (`{"readings": [{"point", "value", "timestamp", "quality", "id"}]}`) |
| `foames.foames_bms.api.list_facility_assets`, `get_facility_asset`, `list_building_alarms`, `get_point_history`, `get_utility_consumption`, `get_facility_summary` | GET | read on the DocType concerned | Building management reads |
| `foames.foames_bms.doctype.building_alarm.building_alarm.acknowledge` | POST | write on Building Alarm | Acknowledge a building alarm (`alarm`, `note`) |
| `foames.foames_mcp.reads.*` | GET | read on the DocType concerned | Agent-friendly reads used by the MCP tools |
| `foames.foames_mcp.api.mcp` | POST | logged in; each tool checks its own | The MCP endpoint ([MCP tools](Reference-MCP-tools)) |

## ERPNext adapter reads

| Method | Returns |
| --- | --- |
| `foames.foames_adapters.erpnext.api.get_work_order(name)` | A Work Order with operations and required items |
| `foames.foames_adapters.erpnext.api.list_open_work_orders(workstation, limit)` | Submitted Work Orders not yet complete |
| `foames.foames_adapters.erpnext.api.list_open_job_cards(workstation, machine, limit)` | Open Job Cards |
| `foames.foames_adapters.erpnext.api.get_operations()` | The outbox operations and their payload keys |

## Document methods

Callable with `frm.call` or `run_doc_method`: `External Reference.resolve`, `Event Log Source.preview`, `Process Event Log.extract`, `discover`, `check_against`, `export_file`.

## Standard REST

Every DocType is also available through Frappe's standard `/api/resource/<DocType>` endpoints under the usual permissions, for example `/api/resource/Maintenance Plan`. Reports run through `frappe.desk.query_report.run` with `report_name`.
