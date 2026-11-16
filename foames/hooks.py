# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

app_name = "foames"
app_title = "FoaMES"
app_publisher = "CLR Technologies Inc."
app_description = "Process-engineered, ERP-agnostic MES on the Frappe framework"
app_email = ""
app_license = "apache-2.0"

# Apps
# ------------------

# The core depends on the Frappe framework only. ERP systems such as ERPNext are optional and are
# reached through the adapters registered below, never through direct Link fields.
# required_apps = []

# ERP Adapters
# ------------
# Each entry is a dotted path to a class implementing foames.foames_adapters.base.ERPAdapter.
# Other apps can register their own adapters (for example an SAP S/4HANA adapter) with this hook.

foames_erp_adapters = [
	"foames.foames_adapters.erpnext.ERPNextAdapter",
	"foames.foames_adapters.s4hana.adapter.S4HANAAdapter",
	"foames.foames_adapters.insights_hub.adapter.InsightsHubAdapter",
	# Other MES and MOM systems, each a profile over the shared REST framework in foames_adapters.mes.
	"foames.foames_adapters.plex.adapter.PlexAdapter",
	"foames.foames_adapters.factorytalk_productioncentre.adapter.FactoryTalkProductionCentreAdapter",
	"foames.foames_adapters.sap_dmc.adapter.SAPDigitalManufacturingAdapter",
	"foames.foames_adapters.delmia_apriso.adapter.DelmiaAprisoAdapter",
	"foames.foames_adapters.aveva_mes.adapter.AvevaMESAdapter",
	"foames.foames_adapters.critical_manufacturing.adapter.CriticalManufacturingAdapter",
	"foames.foames_adapters.tulip.adapter.TulipAdapter",
	"foames.foames_adapters.aegis_factorylogix.adapter.AegisFactoryLogixAdapter",
	"foames.foames_adapters.koerber_pasx.adapter.KoerberPASXAdapter",
	"foames.foames_adapters.proficy.adapter.ProficyAdapter",
]

# IDocs received from S/4HANA, by message type. Each handler is called with the S4HANA Inbound IDoc
# record, the parsed IDoc and its summary, after the IDoc's External Reference has been recorded.
# foames_s4hana_idoc_handlers = {
# 	"LOIPRO": ["myapp.s4hana.on_order_download"],
# }

# Installation
# ------------

before_install = "foames.install.before_install"
after_install = "foames.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "foames.uninstall.before_uninstall"
# after_uninstall = "foames.uninstall.after_uninstall"

# Document Events
# ---------------
# ERPNext records the adapter maps keep their External References current. These DocTypes exist
# only when ERPNext is installed; on a plain Frappe site the entries are inert, and the handlers
# check the adapter is available before touching anything.

_erpnext_reference_sync = {
	"on_update": "foames.foames_adapters.erpnext.sync.on_update",
	"on_update_after_submit": "foames.foames_adapters.erpnext.sync.on_update",
	"on_trash": "foames.foames_adapters.erpnext.sync.on_trash",
	"after_rename": "foames.foames_adapters.erpnext.sync.after_rename",
}

doc_events = {
	# A closed Downtime Record becomes an ERPNext Downtime Entry when the adapter is told to post them.
	"Downtime Record": {"on_update": "foames.foames_adapters.erpnext.downtime.on_update"},
	# A started Maintenance Work Order becomes an ERPNext Asset Repair on the machine's Asset.
	"Maintenance Work Order": {"on_update": "foames.foames_adapters.erpnext.maintenance.on_update"},
} | {
	doctype: _erpnext_reference_sync
	for doctype in (
		"Item",
		"UOM",
		"Batch",
		"Serial No",
		"Work Order",
		"Operation",
		"Warehouse",
		"Stock Entry",
		"Job Card",
		"BOM",
		"Routing",
		"Workstation",
		"Asset",
	)
}
# A Manufacture entry FoaMES left as a draft gets its serial numbers when a person submits it.
doc_events["Stock Entry"] = {
	**doc_events["Stock Entry"],
	"on_submit": "foames.foames_adapters.erpnext.sync.on_submit",
}
# Machines follow the Job Cards people start, complete, cancel or delete in ERPNext.
doc_events["Job Card"] = {
	**_erpnext_reference_sync,
	# on_change also runs after ERPNext sets the card's status with db_set, which is how Start Job
	# marks a card Work In Progress on v16 without saving it, and how a draft is discarded.
	"on_change": "foames.foames_adapters.erpnext.follow.on_job_card_change",
	"on_trash": [
		_erpnext_reference_sync["on_trash"],
		"foames.foames_adapters.erpnext.follow.on_job_card_trash",
	],
}

# Read-only mode
# --------------
# Every write to another system passes one gate, foames.foames_kernel.write_gate. While a connector
# is read-only (the default for a new site and for every new connector), its writes wait as Pending
# Writes for an authorised operator's electronic sign-off, or are refused, and each step is logged
# against its work order, Job Card or process run in the Write Audit Log. See docs/read-only-mode.md.
#
# The adapter outboxes the gate holds: outbox DocType -> its connector key, or "field:<fieldname>"
# when each row names its connector. The outbox's claim() asks the gate before it sends a posting.
foames_write_gated_outboxes = {
	"ERPNext Outbox": "ERPNext",
	"S4HANA Outbox": "S4HANA",
	"Insights Hub Outbox": "INSIGHTS_HUB",
	"MES Outbox": "field:connection",
}
doc_events |= {
	doctype: {
		"after_insert": "foames.foames_kernel.write_gate.outbox_queued",
		"on_update": "foames.foames_kernel.write_gate.outbox_updated",
	}
	for doctype in foames_write_gated_outboxes
}
# Writes that do not go through an outbox (a SCADA or historian write, a change a connector asks
# FoaMES to make) are registered here and requested with write_gate.request_write(connector, key,
# arguments), which performs them, holds them for sign-off, or refuses them.
# foames_write_actions = {"myapp.write_setpoint": "myapp.scada.write_setpoint"}
#
# Other apps add tools to the MCP server with this hook: dotted paths of functions that return a list
# of foames.foames_mcp.protocol.Tool. Their writes pass the gate like the core's.
foames_mcp_tools = [
	"foames.foames_adapters.tulip.reads.mcp_tools",
	# Building management: facility assets, building alarms, point history, utility consumption.
	"foames.foames_bms.api.mcp_tools",
]

# Permissions
# -----------
# A Private recognition is seen only by the person recognized, the giver and supervisors.

has_permission = {"Recognition": "foames.foames_mes.doctype.recognition.recognition.has_permission"}
permission_query_conditions = {
	"Recognition": "foames.foames_mes.doctype.recognition.recognition.get_permission_query_conditions"
}

# Machine data and the floor
# --------------------------
# Other apps extend the MES module through these hooks. Each entry is a dotted path.
#
# foames_machine_event_handlers = ["myapp.floor.on_machine_event"]  # (event, machine) after processing
# foames_floor_snapshot_extensions = ["myapp.floor.extend_snapshot"]  # (snapshot, since, now) in place
# foames_suggestion_rules = ["myapp.floor.my_rule"]  # (snapshot) -> list of finding dicts
# foames_machine_job_changed = ["myapp.floor.on_job_changed"]  # (machine, previous_reference, at)
# foames_machine_state_changed = ["myapp.floor.on_state_changed"]  # (machine, previous_state, state, at)
#
# The ERPNext adapter uses the same hooks to put each machine's open Job Cards on the floor, to
# roll a machine's counts and run time up to the Job Card it is working on, to inspect the Job Card
# a machine finished from what it measured, and to mirror each machine's state onto its ERPNext
# Workstation.
# The S/4HANA adapter rolls them up to the order operation a machine is working on, as partial confirmations.
# The Insights Hub adapter writes them as time series records on the machine's asset, for Opcenter Intelligence.

foames_floor_snapshot_extensions = [
	"foames.foames_adapters.erpnext.floor.extend_snapshot",
	"foames.foames_adapters.erpnext.rollup.mark_current_job_cards",
	# The data layer on Floor View: bound signals and their freshness per machine.
	"foames.foames_topology.floor.extend_snapshot",
	# Lineside bins and material queues, and each machine's hours to dry.
	"foames.foames_mes.material_flow.extend_snapshot",
	# Each machine's current and next operations from the published Production Schedule.
	"foames.foames_mes.doctype.production_schedule.production_schedule.extend_snapshot",
	# Building systems: assets in alarm or stale per system, and the open building alarms.
	"foames.foames_bms.floor.extend_snapshot",
]
foames_suggestion_rules = [
	"foames.foames_adapters.erpnext.floor.running_without_job_card",
	"foames.foames_adapters.erpnext.rollup.current_job_card_not_open",
	"foames.foames_adapters.s4hana.rollup.confirmation_rejected",
	"foames.foames_adapters.insights_hub.rollup.posting_rejected",
	# P&ID instruments linked to a machine that stopped reporting or read at a range limit.
	"foames.foames_pid.rules.instrument_signals",
	# A machine reporting Running while an active permit holds locks on it.
	"foames.foames_ehs.rules.running_under_lockout",
	"foames.foames_mes.doctype.production_schedule.production_schedule.behind_schedule",
]
foames_machine_job_changed = [
	"foames.foames_adapters.erpnext.rollup.on_job_changed",
	"foames.foames_adapters.erpnext.quality.on_job_changed",
	"foames.foames_adapters.s4hana.rollup.on_job_changed",
	"foames.foames_adapters.insights_hub.rollup.on_job_changed",
]
foames_machine_state_changed = [
	"foames.foames_adapters.erpnext.workstation.on_state_changed",
	"foames.foames_adapters.insights_hub.rollup.on_state_changed",
	# Raises a Critical suggestion the moment a machine under an active lockout permit reports Running.
	"foames.foames_ehs.rules.on_state_changed",
]

# Production scheduling
# ---------------------
# Demand sources fill a Production Schedule's rows ("Get Operations"). Each dotted path is called with
# (start, end, line) and returns a list of Production Schedule Job values. The ERPNext adapter adds its
# open Job Cards; it only reads ERPNext.
#
# Cycle time estimators answer how many seconds one unit takes on a machine when a row gives no run
# time or cycle time. Each is called with (row: dict, machine: dict) and returns seconds or None; the
# first answer wins, and the machine's Ideal Cycle Seconds is the fallback.
# foames_cycle_time_estimators = ["myapp.timing.seconds_per_unit"]

foames_schedule_demand_sources = [
	"foames.foames_adapters.erpnext.schedule.demand",
]

# Material flow
# -------------
# Lineside stock is read from the ERP, never written. Each stock reader is called with (item, location)
# and returns a dict with at least actual_qty, or None when it does not know the item; the first answer
# wins. The ERPNext adapter reads its Bin table.
# foames_stock_readers = ["myapp.stock.read_stock"]

foames_stock_readers = [
	"foames.foames_adapters.erpnext.stock.read_stock",
]

# Process mining
# --------------
# Other apps add events to the process-mining event log. Each dotted path is called with
# (since, until) and returns an iterable of foames.foames_process_mining.eventlog.Event.
#
# foames_process_event_extractors = ["myapp.mining.job_events"]

# Topology
# --------
# Other apps add assets, links and signal bindings to the topology graph. Each dotted path is
# called with no arguments during the topology sync and returns a collector report (see
# foames.foames_topology.ingest), checked the same way as one posted to the ingest API.
#
# foames_topology_collectors = ["myapp.topology.report"]
#
# The building management module reports its facility zones, assets and points this way.

foames_topology_collectors = ["foames.foames_bms.topology.report"]

# Commissioning
# -------------
# Other apps take part in equipment handover through these hooks. Each entry is a dotted path.
#
# foames_commissioning_readiness_checks = ["myapp.qualification.blockers"]  # (package) -> list of blocker dicts
# foames_commissioning_handed_over = ["myapp.qualification.on_handover"]  # (package) after handover

# Scheduled Tasks
# ---------------

scheduler_events = {
	"all": [
		# Sends due postings to S/4HANA; does nothing unless the S/4HANA adapter is enabled.
		"foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox.process_outbox",
		# Performs due postings to ERPNext; does nothing unless postings are enabled in ERPNext Adapter Settings.
		"foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox.process_outbox",
		# Sends due writes to Insights Hub; does nothing unless the Insights Hub adapter is enabled.
		"foames.foames_adapters.doctype.insights_hub_outbox.insights_hub_outbox.process_outbox",
		# Sends due writes to the other MES systems; does nothing without an enabled MES Connection.
		"foames.foames_adapters.doctype.mes_outbox.mes_outbox.process_outbox",
	],
	"cron": {
		"*/5 * * * *": [
			"foames.foames_mes.tasks.mark_stale_machines_unknown",
			# Raises an Agent Suggestion for each Andon Call that misses its call type's targets.
			"foames.foames_mes.doctype.andon_call.andon_call.escalate_andon_calls",
			# Raises a communication-loss Building Alarm for each building point that stopped reporting.
			"foames.foames_bms.tasks.check_stale_points",
		],
		# Rolls machine counts up to ERPNext Job Cards, to S/4HANA confirmations and to Insights Hub time
		# series; each does nothing unless enabled in its adapter's settings.
		# Mirrors Machines, machine data sources, P&ID components, OEE and ERP references into the
		# topology graph; does nothing when sync is off in Topology Settings.
		"*/15 * * * *": ["foames.foames_topology.sync.scheduled_sync"],
		"*/10 * * * *": [
			"foames.foames_adapters.erpnext.rollup.roll_up_all",
			"foames.foames_adapters.s4hana.rollup.roll_up_all",
			"foames.foames_adapters.insights_hub.rollup.roll_up_all",
			# Reads lineside stock, forecasts when each line runs dry, keeps queue readiness current and
			# raises suggestions for bins running dry, queue-time limits, starved machines and full buffers.
			"foames.foames_mes.tasks.check_material_flow",
		],
		# Monday 06:00, after the daily OEE run has closed Sunday: highlights per line for the week
		# that just ended; does nothing when turned off.
		"0 6 * * 1": ["foames.foames_mes.tasks.recognize_team_highlights"],
	},
	"hourly": [
		"foames.foames_mes.tasks.run_suggestion_rules",
		# Reads every Maintenance Plan's meter and raises suggestions for plans coming due.
		"foames.foames_mes.tasks.check_maintenance_plans",
		# Expires permits to work, and raises suggestions for overdue safety actions, investigations and reviews.
		"foames.foames_ehs.tasks.check_ehs",
		# Raises suggestions for Critical and High building alarms nobody acknowledged, and for hazardous
		# material storage with no active hazard assessment or no monitored point.
		"foames.foames_bms.tasks.check_bms",
	],
	"daily": [
		# Raises suggestions for risks above tolerance, overdue risk reviews and control verifications,
		# failed controls, breached key risk indicators and linked assessments that now rate higher.
		"foames.foames_risk.tasks.check_risks",
		"foames.foames_mes.tasks.compute_daily_oee",
		# Looks up External References that are still Unverified or Missing in their ERP.
		"foames.foames_kernel.tasks.refresh_external_references",
		# Raises suggestions for NPI gates that are due or overdue and for overdue gate conditions.
		"foames.foames_life_sciences.tasks.check_npi_gates",
		# Recognizes people for the milestones they reached; does nothing when turned off.
		"foames.foames_mes.tasks.recognize_milestones",
		# Raises suggestions for overdue commissioning punch items and packages past their planned handover.
		"foames.foames_commissioning.tasks.check_commissioning",
		# Reads the floor for every Released PFMEA and raises review suggestions where it disagrees.
		"foames.foames_mes.tasks.check_pfmeas",
		# Raises suggestions for equipment and process qualifications that are due soon or expired.
		"foames.foames_validation.tasks.check_requalification",
		# Makes approved SOP revisions effective on their date and raises suggestions for SOP reviews
		# coming due and for people not trained on the current revision in time.
		"foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure.check_sops",
	],
}

# Enterprise risk management
# --------------------------
# A "Create > Enterprise Risk" button on the detailed assessments a risk can summarise. The forms
# exist only when their modules are installed; on a site without them the entries are inert.
doctype_js = {
	"Hazard Assessment": "public/js/risk_source.js",
	"PFMEA": "public/js/risk_source.js",
}
#
# Other apps extend the risk register through these hooks; see foames/foames_risk/register.py.
#
# foames_risk_linkable_doctypes = ["My Audit Finding"]  # record types a risk may link to
# foames_risk_source_readers = {"My Assessment": "myapp.risk.rating"}  # (doctype, name) -> rating or None
# foames_risk_source_values = {"My Assessment": "myapp.risk.new_risk"}  # (doctype, name) -> risk fields
# foames_risk_evidence_checks = ["myapp.risk.evidence_problem"]  # (doctype, name) -> problem or None

# Testing
# -------

before_tests = "foames.install.before_tests"
