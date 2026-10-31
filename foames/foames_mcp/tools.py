# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The MCP tool catalogue: every tool, the whitelisted FoaMES method it calls and its input schema.

This is the whole public surface an agent sees. Each tool maps one to one onto a method that is
already callable at `/api/method/<method>`, so the MCP server adds no capability that the HTTP
API does not have and enforces no permission of its own: the method checks Frappe permissions for
the user the API key belongs to.

Tools read the plant (machines, events, downtime, OEE, the floor snapshot, suggestions, process
mining, ERP references). The only writes are `foames_post_suggestion` and
`foames_run_suggestion_rules`, which create Agent Suggestions for people to act on, and
`foames_set_current_job`, which records which job a machine is on. Agents suggest; people act.
"""

from __future__ import annotations

from foames.foames_mcp.protocol import Tool

MES_API = "foames.foames_mes.api"
OEE = "foames.foames_mes.doctype.oee_period.oee_period"
MINING = "foames.foames_process_mining.api"
ADAPTERS = "foames.foames_adapters"
READS = "foames.foames_mcp.reads"

# Packages a tool's method may live in. The catalogue test holds every tool to this list, so a
# tool cannot quietly reach a method outside the public API.
ALLOWED_METHOD_PREFIXES = (MES_API, OEE, MINING, ADAPTERS + ".get_available_erp_systems", READS)

INSTRUCTIONS = """FoaMES is a manufacturing execution system. These tools read the plant floor and \
raise suggestions. Rules: suggest, never act (releases, holds, dispositions and ERP postings are done \
by people); quote the numbers you relied on in `evidence`; time without a machine signal is loss, \
never production, so do not infer output from silence. Start with foames_get_floor_snapshot for the \
whole floor, foames_list_machines for one machine at a time, foames_get_oee for any window, and the \
foames_mining_* tools for how work really flows. Datetimes are the site's local time, \
formatted YYYY-MM-DD HH:MM:SS."""


def _s(description: str, **extra) -> dict:
	return {"type": "string", "description": description, **extra}


def _i(description: str, **extra) -> dict:
	return {"type": "integer", "description": description, **extra}


def _b(description: str) -> dict:
	return {"type": "boolean", "description": description}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
	schema = {"type": "object", "properties": properties, "additionalProperties": False}
	if required:
		schema["required"] = required
	return schema


LIMIT = _i("Maximum rows to return (default 100, at most 1000)", minimum=1, maximum=1000)
SINCE = _s("Start of the window, inclusive (YYYY-MM-DD HH:MM:SS or an ISO 8601 datetime)")
UNTIL = _s("End of the window, exclusive (YYYY-MM-DD HH:MM:SS or an ISO 8601 datetime)")
MACHINE = _s("Machine code (the name of the Machine record)")

WINDOW_AND_SOURCES = {
	"event_log": _s("Name of a saved Process Event Log to analyse instead of building a log now"),
	"since": SINCE,
	"until": UNTIL,
	"sources": {
		"type": "array",
		"items": {"type": "string"},
		"description": "Event Log Source names to include; omit for every enabled source",
	},
}

MACHINE_STATES = ["Unknown", "Running", "Idle", "Down", "Setup"]
EVENT_TYPES = ["State", "Count", "Measurement", "Alarm", "Message"]
SUGGESTION_CATEGORIES = ["Yield", "Downtime", "Quality", "Release", "Machine Data", "ERP", "Other"]
SEVERITIES = ["Info", "Warning", "Critical"]
SUGGESTION_STATUSES = ["Open", "Accepted", "Dismissed", "Done"]
REFERENCE_STATUSES = ["Unverified", "Resolved", "Missing"]

TOOLS: list[Tool] = [
	# Machines and state --------------------------------------------------------------------
	Tool(
		name="foames_list_machines",
		title="List machines",
		description="Machines with their current state, when they last reported, when they last counted a part, their ideal cycle time and shift. Needs read on Machine.",
		method=f"{READS}.list_machines",
		input_schema=_schema(
			{
				"status": _s("Only machines in this state", enum=MACHINE_STATES),
				"machine_type": _s("Only machines of this type (free text on the Machine)"),
				"include_disabled": _b("Include disabled machines (default false)"),
				"limit": LIMIT,
			}
		),
	),
	Tool(
		name="foames_get_machine",
		title="Get a machine",
		description="One machine in detail: its settings, counts over the last 24 hours, the open downtime if any, its latest OEE Period and its most recent state changes. Needs read on Machine; the sections the user may not read are left out.",
		method=f"{READS}.get_machine",
		input_schema=_schema({"machine": MACHINE}, ["machine"]),
	),
	Tool(
		name="foames_list_machine_events",
		title="List machine events",
		description="Raw machine events (state changes, counter readings with the delta FoaMES computed, measurements, alarms, messages), newest first. Needs read on Machine Event.",
		method=f"{READS}.list_machine_events",
		input_schema=_schema(
			{
				"machine": MACHINE,
				"event_type": _s("Only events of this type", enum=EVENT_TYPES),
				"since": SINCE,
				"until": UNTIL,
				"limit": LIMIT,
			}
		),
	),
	# Downtime ------------------------------------------------------------------------------
	Tool(
		name="foames_list_downtime",
		title="List downtime records",
		description="Downtime Records (open or closed) with reason, start, end and duration, newest first. Needs read on Downtime Record.",
		method=f"{READS}.list_downtime",
		input_schema=_schema(
			{
				"machine": MACHINE,
				"status": _s("Open or Closed", enum=["Open", "Closed"]),
				"reason": _s("Only records with this Downtime Reason code"),
				"since": _s("Only records that started at or after this datetime"),
				"until": _s("Only records that started before this datetime"),
				"limit": LIMIT,
			}
		),
	),
	Tool(
		name="foames_downtime_by_reason",
		title="Downtime by reason",
		description="Minutes of downtime per reason for one machine inside a window, counting the part of each record that overlaps it; open downtime counts up to the end of the window. Unclassified downtime is reported separately. Defaults to the last 24 hours. Needs read on Downtime Record.",
		method=f"{READS}.downtime_by_reason",
		input_schema=_schema({"machine": MACHINE, "since": SINCE, "until": UNTIL}, ["machine"]),
	),
	Tool(
		name="foames_list_downtime_reasons",
		title="List downtime reasons",
		description="The Downtime Reason codes a site uses, with their category and whether they count as planned downtime (excluded from the OEE availability base). Needs read on Downtime Reason.",
		method=f"{READS}.list_downtime_reasons",
	),
	# OEE -----------------------------------------------------------------------------------
	Tool(
		name="foames_get_oee",
		title="OEE for any window",
		description="Availability, performance, quality and OEE for one machine over any window, computed now from its events and downtime without saving a period, with the time ledger (run, unknown minutes, coverage), counts and notes. Needs read on OEE Period.",
		method=f"{OEE}.get_oee",
		input_schema=_schema(
			{
				"machine": MACHINE,
				"from_time": _s("Start of the window (YYYY-MM-DD HH:MM:SS)"),
				"to_time": _s("End of the window (YYYY-MM-DD HH:MM:SS)"),
				"planned_minutes": {
					"type": "number",
					"description": "Planned production minutes in the window; defaults to its whole length",
				},
			},
			["machine", "from_time", "to_time"],
		),
	),
	Tool(
		name="foames_list_oee_periods",
		title="List OEE periods",
		description="Saved OEE Periods (the scheduler computes one per machine per day), newest first, with the full time ledger. Needs read on OEE Period.",
		method=f"{READS}.list_oee_periods",
		input_schema=_schema(
			{
				"machine": MACHINE,
				"since": _s("Only periods starting at or after this datetime"),
				"until": _s("Only periods starting before this datetime"),
				"limit": LIMIT,
			}
		),
	),
	# Floor and suggestions -----------------------------------------------------------------
	Tool(
		name="foames_get_floor_snapshot",
		title="Floor snapshot",
		description="The whole floor as one object: every enabled machine with its state, counts over the window, minutes since its last count and latest OEE; downtime per machine with the top reason; ERP references that resolved as Missing; open suggestions; and any section another app adds. Needs read on Machine.",
		method=f"{MES_API}.get_floor_snapshot",
		input_schema=_schema({"days": _i("Window in days (default 1)", minimum=1, maximum=90)}),
	),
	Tool(
		name="foames_list_suggestions",
		title="List suggestions",
		description="Agent Suggestions, open ones by default, with category, severity, the agent that raised them and what they refer to. Needs read on Agent Suggestion.",
		method=f"{READS}.list_suggestions",
		input_schema=_schema(
			{
				"status": _s(
					"Filter by status; use 'all' for every status (default Open)",
					enum=[*SUGGESTION_STATUSES, "all"],
				),
				"category": _s("Only this category", enum=SUGGESTION_CATEGORIES),
				"severity": _s("Only this severity", enum=SEVERITIES),
				"agent": _s("Only suggestions raised by this agent id"),
				"limit": LIMIT,
			}
		),
	),
	Tool(
		name="foames_get_suggestion",
		title="Get a suggestion",
		description="One Agent Suggestion in full: the suggestion text, its evidence and its resolution. Needs read on Agent Suggestion.",
		method=f"{READS}.get_suggestion",
		input_schema=_schema({"name": _s("The suggestion's name, for example SUG-2026-00012")}, ["name"]),
	),
	Tool(
		name="foames_post_suggestion",
		title="Post a suggestion",
		description="Raise one Agent Suggestion for people to act on. Give a stable rule_key for a finding so the same finding is not raised again while it is open; a resolved suggestion with that key is reopened with the new evidence. Returns the suggestion's name. Needs create on Agent Suggestion.",
		method=f"{MES_API}.post_suggestion",
		input_schema=_schema(
			{
				"title": _s("Short title"),
				"category": _s("Category", enum=SUGGESTION_CATEGORIES),
				"suggestion": _s("What a person should consider doing, and why"),
				"agent": _s("Your agent id, for example 'claude-floor-agent'"),
				"severity": _s("Severity (default Warning)", enum=SEVERITIES),
				"reference_doctype": _s("DocType the suggestion is about, for example Machine"),
				"reference_name": _s("Name of that record"),
				"evidence": {
					"type": "object",
					"description": "The numbers the suggestion rests on, so a person can check them",
					"additionalProperties": True,
				},
				"rule_key": _s("Stable key for this finding, for example 'downtime:M-01:No Material'"),
			},
			["title", "category", "suggestion", "agent"],
		),
		read_only=False,
		idempotent=False,
	),
	Tool(
		name="foames_run_suggestion_rules",
		title="Run the suggestion rules",
		description="Run the built-in rules (silent or stalled machines, dominant downtime reason, missing ERP references) and any rule another app registered, now, and return the suggestions created. The scheduler runs them hourly. Needs create on Agent Suggestion.",
		method=f"{MES_API}.run_suggestion_rules",
		input_schema=_schema({"days": _i("Window in days (default 1)", minimum=1, maximum=90)}),
		read_only=False,
	),
	Tool(
		name="foames_set_current_job",
		title="Set a machine's current job",
		description="Tell FoaMES which job a machine is working on, so its counts and run time from that moment belong to the job and the ERP adapter can roll up the job that ended. `reference` is the name of an External Reference of type Job Card (any ERP); omit it to end the current job. Changes no ERP record. Needs write on Machine.",
		method=f"{MES_API}.set_current_job",
		input_schema=_schema(
			{
				"machine": MACHINE,
				"reference": _s("External Reference name of the Job Card; omit to end the current job"),
				"at": _s("When the job started or ended (default now; YYYY-MM-DD HH:MM:SS)"),
			},
			["machine"],
		),
		read_only=False,
	),
	# Process mining ------------------------------------------------------------------------
	Tool(
		name="foames_mining_summary",
		title="Event log summary",
		description="Counts of events, cases, variants and activities in the event log for a window (built on the fly from machine states, downtime and every enabled Event Log Source) or for a saved Process Event Log. Needs read on Process Event Log.",
		method=f"{MINING}.summary",
		input_schema=_schema(WINDOW_AND_SOURCES),
	),
	Tool(
		name="foames_mining_events",
		title="Event log events",
		description="The events themselves (case, activity, lifecycle, timestamp, resource, objects, attributes). Needs read on Process Event Log.",
		method=f"{MINING}.events",
		input_schema=_schema({**WINDOW_AND_SOURCES, "limit": _i("Maximum events (default 1000)", minimum=1)}),
	),
	Tool(
		name="foames_mining_discover",
		title="Discover the process",
		description="Process discovery: the directly-follows graph, the variant table, throughput, activity durations and waits, bottlenecks and rework for the log. Needs read on Process Event Log.",
		method=f"{MINING}.discover",
		input_schema=_schema(
			{
				**WINDOW_AND_SOURCES,
				"min_edge_count": _i("Drop edges seen fewer times than this (default 1)", minimum=1),
				"dot": _b("Also return the graph in Graphviz DOT"),
			}
		),
	),
	Tool(
		name="foames_mining_conformance",
		title="Check conformance",
		description="Replay the log on a reference model and report fitness, deviations per trace and the footprint comparison. The model is a DFG object as returned by foames_mining_discover, a list of activity names for a strict sequence, or the name of a saved Process Event Log whose discovered graph is the reference. Needs read on Process Event Log.",
		method=f"{MINING}.check_conformance",
		input_schema=_schema(
			{
				"model": {
					"type": ["object", "array", "string"],
					"description": "The reference model (DFG object, list of activities, or a Process Event Log name)",
				},
				**WINDOW_AND_SOURCES,
				"include_traces": _b("Include the per-trace deviations (default true)"),
			},
			["model"],
		),
	),
	Tool(
		name="foames_mining_export",
		title="Export the event log",
		description="The log as XES XML or OCEL 2.0 JSON text, for an external process-mining tool. Needs read on Process Event Log.",
		method=f"{MINING}.export",
		input_schema=_schema(
			{**WINDOW_AND_SOURCES, "fmt": _s("xes (default) or ocel", enum=["xes", "ocel"])}
		),
	),
	Tool(
		name="foames_list_event_logs",
		title="List saved event logs",
		description="Saved Process Event Logs with their window, status and counts. Needs read on Process Event Log.",
		method=f"{READS}.list_event_logs",
		input_schema=_schema(
			{"status": _s("Only logs in this status", enum=["Draft", "Extracted", "Failed"]), "limit": LIMIT}
		),
	),
	Tool(
		name="foames_list_event_log_sources",
		title="List event log sources",
		description="The Event Log Sources configured on the site: which DocType each mines and how its case, activity, timestamps and resource are mapped. Needs read on Event Log Source.",
		method=f"{READS}.list_event_log_sources",
	),
	# ERP references ------------------------------------------------------------------------
	Tool(
		name="foames_list_erp_systems",
		title="List ERP systems",
		description="The ERP adapters registered on the site (for example ERPNext, S/4HANA), whether each can be reached, the default system, and the reference types the kernel understands.",
		method=f"{READS}.list_erp_systems",
	),
	Tool(
		name="foames_list_external_references",
		title="List ERP references",
		description="External References: the ERP records FoaMES points at (items, work orders, workstations and so on), with their resolution status and label. Needs read on External Reference.",
		method=f"{READS}.list_external_references",
		input_schema=_schema(
			{
				"erp_system": _s("Only references into this ERP system key"),
				"reference_type": _s("Only this kernel reference type, for example Work Order"),
				"status": _s("Only this status", enum=REFERENCE_STATUSES),
				"limit": LIMIT,
			}
		),
	),
	Tool(
		name="foames_lookup_erp_record",
		title="Look up an ERP record",
		description="Read one record from an ERP through its adapter (ERPNext on the same site, or S/4HANA over OData) and return its label and the data the adapter exposes. Reads only; creates no External Reference and changes nothing in the ERP. Needs read on External Reference.",
		method=f"{READS}.lookup_erp_record",
		input_schema=_schema(
			{
				"reference_type": _s("Kernel reference type, for example Item, Work Order, Workstation"),
				"external_id": _s("The record's id in the ERP"),
				"erp_system": _s("ERP system key; defaults to the site's default ERP system"),
			},
			["reference_type", "external_id"],
		),
	),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
