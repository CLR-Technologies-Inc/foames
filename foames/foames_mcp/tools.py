# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The MCP tool catalogue: every tool, the whitelisted FoaMES method it calls and its input schema.

This is the whole public surface an agent sees. Each tool maps one to one onto a method that is
already callable at `/api/method/<method>`, so the MCP server adds no capability that the HTTP
API does not have and enforces no permission of its own: the method checks Frappe permissions for
the user the API key belongs to.

Tools read the plant (machines, events, downtime, OEE, the floor snapshot, suggestions, process
mining, ERP references). The only writes are `foames_post_suggestion` and
`foames_run_suggestion_rules`, which create Agent Suggestions for people to act on, and
`foames_set_current_job`, which records which job a machine is on. Agents suggest; people act.

Read-only mode: while the site or the MCP server's Connector Write Policy is read-only, a call to a
writing tool other than the suggestion tools does not run. It waits as a Pending Write for an
authorised person's electronic sign-off (or is refused), and the agent is told so. The
`foames_*write*` tools below read the mode, the waiting writes and the audit trail; no tool signs.
"""

from __future__ import annotations

from foames.foames_mcp.protocol import Tool

MES_API = "foames.foames_mes.api"
OEE = "foames.foames_mes.doctype.oee_period.oee_period"
MINING = "foames.foames_process_mining.api"
ADAPTERS = "foames.foames_adapters"
READS = "foames.foames_mcp.reads"
CYCLE = "foames.foames_mes.cycle_time_api"
LIFESCI = "foames.foames_life_sciences.api"
GATE = "foames.foames_kernel.write_gate"
PID = "foames.foames_pid.api"
VALIDATION = "foames.foames_validation.api"

# Packages a tool's method may live in. The catalogue test holds every tool to this list, so a
# tool cannot quietly reach a method outside the public API.
ALLOWED_METHOD_PREFIXES = (
	MES_API,
	OEE,
	MINING,
	ADAPTERS + ".get_available_erp_systems",
	READS,
	CYCLE,
	LIFESCI,
	GATE + ".get_write_mode",
	GATE + ".list_pending_writes",
	GATE + ".get_write_audit_trail",
	# The P&ID reads only; importing a register and applying links stay with people on the desk.
	*(
		f"{PID}.{method}"
		for method in (
			"list_components",
			"get_component",
			"get_drawing",
			"parse_instrument_tag",
			"suggest_links",
		)
	),
	VALIDATION + ".get_qualification_status",
)

INSTRUCTIONS = """FoaMES is a manufacturing execution system. These tools read the plant floor and \
raise suggestions. Rules: suggest, never act (releases, holds, dispositions and ERP postings are done \
by people); quote the numbers you relied on in `evidence`; time without a machine signal is loss, \
never production, so do not infer output from silence. Start with foames_get_floor_snapshot for the \
whole floor, foames_list_machines for one machine at a time, foames_get_oee for any window, and the \
foames_mining_* tools for how work really flows. FoaMES may be in read-only mode \
(foames_get_write_mode): then a write you ask for is held for a person's electronic sign-off instead \
of being made, and the answer names the Pending Write; do not repeat the call. Datetimes are the site's local time, \
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
SUGGESTION_CATEGORIES = [
	"Yield",
	"Downtime",
	"Quality",
	"Release",
	"Machine Data",
	"ERP",
	"Material",
	"Other",
]
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
	# Material flow -------------------------------------------------------------------------
	Tool(
		name="foames_get_material_status",
		title="Material status",
		description="Lineside bins and material queues as last checked, for the floor or one machine: estimated stock on hand, use per hour, hours until the line runs dry, the quantity to call for, queue waiting and ready counts, and each material's MPC level (Material Processing Complexity 1-5). The ERP stays the inventory system of record; this is FoaMES's lineside view. Needs read on Lineside Bin and Material Queue.",
		method=f"{MES_API}.get_material_status",
		input_schema=_schema({"machine": MACHINE}),
	),
	Tool(
		name="foames_get_dispatch_list",
		title="Material dispatch list",
		description="Material that may start now in one queue, in the order the queue's dispatch rule (FIFO, Priority, Earliest Due, Earliest Expiry) picks it. Leaves out entries still in their minimum wait, past their queue-time limit, expired or on hold; those need a person's decision. Needs read on Material Queue Entry.",
		method=f"{MES_API}.get_dispatch_list",
		input_schema=_schema({"queue": _s("Material Queue name")}, ["queue"]),
	),
	Tool(
		name="foames_get_material_readiness",
		title="Material readiness",
		description="Whether a machine has the material to run for the next hours: lineside bins that run dry inside the window (or are dry now) and queue entries ready to start. Use it before suggesting what a machine should start. Needs read on Lineside Bin and Material Queue Entry.",
		method=f"{MES_API}.get_material_readiness",
		input_schema=_schema(
			{
				"machine": MACHINE,
				"hours": {
					"type": "number",
					"description": "Window in hours (default 0: now only)",
					"minimum": 0,
				},
			},
			["machine"],
		),
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
		suggests=True,
		idempotent=False,
	),
	Tool(
		name="foames_run_suggestion_rules",
		title="Run the suggestion rules",
		description="Run the built-in rules (silent or stalled machines, dominant downtime reason, missing ERP references) and any rule another app registered, now, and return the suggestions created. The scheduler runs them hourly. Needs create on Agent Suggestion.",
		method=f"{MES_API}.run_suggestion_rules",
		input_schema=_schema({"days": _i("Window in days (default 1)", minimum=1, maximum=90)}),
		read_only=False,
		suggests=True,
	),
	Tool(
		name="foames_set_current_job",
		title="Set a machine's current job",
		description="Tell FoaMES which job a machine is working on, so its counts and run time from that moment belong to the job and the ERP adapter can roll up the job that ended. `reference` is the name of an External Reference of type Job Card (any ERP); omit it to end the current job. Changes no ERP record. Needs write on Machine. In read-only mode the change waits for a person's sign-off.",
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
	# P&IDs -------------------------------------------------------------------------------
	Tool(
		name="foames_pid_list_components",
		title="List P&ID components",
		description="The P&ID tag register: equipment, instruments, lines and valves with their ISA-5.1 meaning, the drawing they are on, what they are located on, and the machine and signal that carry their live value. Needs read on PID Component.",
		method=f"{PID}.list_components",
		input_schema=_schema(
			{
				"drawing": _s("Only components on this P&ID drawing number"),
				"component_type": _s(
					"Only this type", enum=["Equipment", "Instrument", "Line", "Valve", "Actuator", "Other"]
				),
				"machine": MACHINE,
				"linked": _i(
					"1: only components linked to a machine; 0: only those not linked", minimum=0, maximum=1
				),
				"search": _s("Text to find in the tag or description"),
				"limit": LIMIT,
			}
		),
	),
	Tool(
		name="foames_pid_get_component",
		title="Get a P&ID component",
		description="One tag in detail: its register entry, the ISA-5.1 reading of the tag, its latest value with a flag (high or low: at a calibrated range limit; stale; none: never reported), the components located on it and its process and signal connections on the drawings. Needs read on PID Component.",
		method=f"{PID}.get_component",
		input_schema=_schema({"tag": _s("The tag, for example FIC-101 or P-101")}, ["tag"]),
	),
	Tool(
		name="foames_pid_get_drawing",
		title="Get a P&ID drawing",
		description="A P&ID drawing's title block, every component on it and its process and signal connections (what feeds what, along which line). Use it to reason about what is upstream or downstream of a machine or instrument. Needs read on PID Drawing.",
		method=f"{PID}.get_drawing",
		input_schema=_schema({"drawing": _s("The drawing number")}, ["drawing"]),
	),
	Tool(
		name="foames_pid_parse_tag",
		title="Read an instrument tag",
		description="Read an instrument tag by the ISA-5.1 identification letters: measured variable, modifiers, functions (indicate, control, transmit, switch, alarm, valve ...), loop number. Works on any tag; needs no record.",
		method=f"{PID}.parse_instrument_tag",
		input_schema=_schema({"tag": _s("An instrument tag, for example PDT-2003A or 10-LSHH-305")}, ["tag"]),
	),
	Tool(
		name="foames_pid_suggest_links",
		title="Suggest P&ID signal links",
		description="Candidate links between unlinked P&ID tags and the machines and signals FoaMES receives (machine codes, mapped OPC UA nodes and Sparkplug metrics, measurement names seen in the last 30 days), each with its reason. Reads only: a person applies links on the desk. Needs read on PID Component.",
		method=f"{PID}.suggest_links",
		input_schema=_schema({"drawing": _s("Only tags on this drawing")}),
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
	# Cycle time ----------------------------------------------------------------------------
	Tool(
		name="foames_project_time",
		title="Project automatic and manual time",
		description="Elapsed, automatic (machine) and operator (manual) time for a quantity from a Cycle Time Standard, with batch time, parts per hour and cost per part. With `changes` it also projects a what-if scenario (for example an element moved from Manual to Automatic) and returns the baseline, the scenario and their difference; `annual_quantity` adds yearly savings. With `use_observed` the automatic time is first scaled to what the machine did. Needs read on Cycle Time Standard.",
		method=f"{CYCLE}.project_time",
		input_schema=_schema(
			{
				"standard": _s("Cycle Time Standard name; or give machine for its default standard"),
				"machine": MACHINE,
				"quantity": {"type": "number", "description": "Parts to make", "minimum": 0},
				"changes": {
					"type": "array",
					"description": "Scenario changes. Each names an `element` and sets any of kind (Manual or Automatic), seconds, internal, every, per, or remove: true; an unknown element is added. A change without `element` may set parts_per_cycle, allowance_percent, labor_rate or machine_rate.",
					"items": {"type": "object"},
				},
				"annual_quantity": {"type": "number", "description": "Yearly volume, for savings"},
				"use_observed": _b("Scale automatic time to the machine's observed running time first"),
				"days": _i("Days of machine history for use_observed (default 30)", minimum=1),
			},
			["quantity"],
		),
	),
	Tool(
		name="foames_compare_cycle_with_machine",
		title="Compare a cycle standard with the machine",
		description="A Cycle Time Standard's one-cycle automatic and total time next to what its machine did in the window (Running time per cycle; Running plus Idle per cycle), with variances in percent. Idle includes waiting for material, so it is an upper bound on manual time. Needs read on Cycle Time Standard and Machine Event.",
		method=f"{CYCLE}.compare_with_observed",
		input_schema=_schema(
			{
				"standard": _s("Cycle Time Standard name; or give machine for its default standard"),
				"machine": MACHINE,
				"since": SINCE,
				"until": UNTIL,
				"days": _i("Window length in days when since is not given (default 30)", minimum=1),
			}
		),
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
	# Life sciences: NPI, product requirements, tech transfer and PD simulation ---------------
	Tool(
		name="foames_get_npi_status",
		title="Get NPI program status",
		description="New product introduction programs: current stage (Concept, Feasibility, Development, Verification & Validation, Transfer, Launch), status, the next gate and its target date, required deliverables and phase review entry and exit criteria of the current stage still open, the phase review board and the phase reviews held (Phase Review Discipline), open Conditional Go conditions and the decisions so far. Active and on-hold programs unless include_closed. Gate decisions are made by people (the board's Chair where a board governs the program); report readiness, do not decide. Needs read on NPI Program.",
		method=f"{LIFESCI}.get_npi_status",
		input_schema=_schema(
			{
				"program": _s("Only this NPI Program (its name, for example NPI-2026-00001)"),
				"include_closed": _b("Include launched and cancelled programs (default false)"),
			}
		),
	),
	Tool(
		name="foames_get_requirements_trace",
		title="Get the requirements trace matrix",
		description="The trace matrix of a product requirements document: each user need, design input, QTPP element or CQA with what it refines, its design output, verification and validation, the gaps (no acceptance criteria, not verified, failed) and the coverage figures. Needs read on Product Requirements Document.",
		method=f"{LIFESCI}.get_requirements_trace",
		input_schema=_schema({"document": _s("The Product Requirements Document name")}, ["document"]),
	),
	Tool(
		name="foames_get_tech_transfer_package",
		title="Get a tech transfer package",
		description="An MSAT tech transfer package: sending and receiving site, scale, every process parameter with criticality (CPP, KPP), set point, NOR and PAR and scale rule, every quality attribute with limits and comparability approach and the latest comparability outcome, the transfer deliverables and, for a draft, what still blocks approval. Needs read on Tech Transfer Package.",
		method=f"{LIFESCI}.get_tech_transfer_package",
		input_schema=_schema({"package": _s("The Tech Transfer Package name")}, ["package"]),
	),
	Tool(
		name="foames_get_pd_study",
		title="Get a PD simulation study",
		description="A process development study: factors with ranges and operating distributions, responses with limits, the runs and their results, the fitted response-surface models (coefficients in coded units, R squared, RMSE) and the last Monte Carlo what-if. Needs read on PD Simulation Study.",
		method=f"{LIFESCI}.get_pd_study",
		input_schema=_schema({"study": _s("The PD Simulation Study name")}, ["study"]),
	),
	Tool(
		name="foames_scale_up",
		title="Scale up a stirred vessel",
		description="Stirred, aerated vessel scale-up under geometric similarity: for constant P/V, tip speed, Reynolds number and mixing time, the large-scale impeller speed, power, P/V, tip speed, Re, vvm, superficial gas velocity and kLa (van 't Riet), with ratios to the small scale. Arithmetic only; an estimate for engineering judgment.",
		method=f"{LIFESCI}.scale_up",
		input_schema=_schema(
			{
				"small_volume_l": {"type": "number", "description": "Small-scale working volume, litres"},
				"large_volume_l": {"type": "number", "description": "Large-scale working volume, litres"},
				"impeller_diameter_m": {
					"type": "number",
					"description": "Small-scale impeller diameter, metres",
				},
				"rpm": {"type": "number", "description": "Small-scale impeller speed, rpm"},
				"power_number": {
					"type": "number",
					"description": "Impeller power number (default 5, Rushton turbine)",
				},
				"density": {"type": "number", "description": "Broth density, kg/m3 (default 1000)"},
				"viscosity": {"type": "number", "description": "Broth viscosity, Pa s (default 0.001)"},
				"tank_diameter_m": {
					"type": "number",
					"description": "Small-scale vessel diameter, metres (for gas velocity and kLa)",
				},
				"gas_l_min": {"type": "number", "description": "Small-scale gas flow, L/min"},
				"gas_rule": _s(
					"How gas flow scales", enum=["Constant vvm", "Constant Superficial Gas Velocity"]
				),
				"kla_correlation": _s(
					"kLa correlation", enum=["Coalescing (van 't Riet)", "Non-coalescing (van 't Riet)"]
				),
			},
			["small_volume_l", "large_volume_l", "impeller_diameter_m", "rpm"],
		),
	),
	# Read-only mode -------------------------------------------------------------------------
	Tool(
		name="foames_get_write_mode",
		title="Get the read-only mode",
		description="Whether FoaMES is in read-only mode, site-wide and per connector (adapter, MES connection, bridge, this MCP server), what happens to a write (held for sign-off or blocked), the role that signs, and how many writes wait. Needs read on Connector Write Policy.",
		method=f"{GATE}.get_write_mode",
		input_schema=_schema({}),
	),
	Tool(
		name="foames_list_pending_writes",
		title="List pending writes",
		description="Writes held by read-only mode, newest first: what would be written, by which connector, for which work order, Job Card, process run or machine, who asked, and who signed it off with what meaning and reason. Needs read on Pending Write.",
		method=f"{GATE}.list_pending_writes",
		input_schema=_schema(
			{
				"status": _s(
					"Only writes in this status",
					enum=[
						"Awaiting Sign-off",
						"Approved",
						"Released",
						"Executed",
						"Rejected",
						"Blocked",
						"Failed",
						"Withdrawn",
					],
				),
				"connector": _s("Only writes of this connector key"),
				"work_order": _s("Only writes logged against this work order"),
				"job_card": _s("Only writes logged against this Job Card"),
				"process_run": _s("Only writes logged against this process run"),
				"machine": MACHINE,
				"limit": LIMIT,
			}
		),
	),
	Tool(
		name="foames_get_write_audit_trail",
		title="Get the write audit trail",
		description="The Write Audit Log, oldest first: every write requested, held, blocked, signed, rejected, released or executed, and every change to read-only mode, with user, time and reason. Filter by work order, Job Card, process run, machine, Pending Write or connector. Needs read on Write Audit Log.",
		method=f"{GATE}.get_write_audit_trail",
		input_schema=_schema(
			{
				"work_order": _s("Work order the entries are logged against"),
				"job_card": _s("Job Card the entries are logged against"),
				"process_run": _s("Process run the entries are logged against"),
				"machine": MACHINE,
				"pending_write": _s("Name of a Pending Write"),
				"connector": _s("Connector key"),
				"limit": LIMIT,
			}
		),
	),
	Tool(
		name="foames_get_qualification_status",
		title="Get qualification status",
		description="Where each machine and process stands on its equipment qualifications (IQ, OQ, PQ) and process validation (PPQ, CPV): Qualified, Due Soon, Expired, Runs Pending or Not Qualified, with the date it lapses and the approved execution it rests on. Check this before relying on a machine's output for a validated process. Needs read on Validation Execution.",
		method=f"{VALIDATION}.get_qualification_status",
		input_schema=_schema(
			{
				"machine": _s("Only this machine"),
				"process": _s("Only this process"),
				"protocol_type": _s("Only this protocol type", enum=["IQ", "OQ", "PQ", "PPQ", "CPV"]),
			}
		),
	),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
