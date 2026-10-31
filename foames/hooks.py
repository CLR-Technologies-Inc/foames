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
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 	}
# }

# Machine data and the floor
# --------------------------
# Other apps extend the MES module through these hooks. Each entry is a dotted path.
#
# foames_machine_event_handlers = ["myapp.floor.on_machine_event"]  # (event, machine) after processing
# foames_floor_snapshot_extensions = ["myapp.floor.extend_snapshot"]  # (snapshot, since, now) in place
# foames_suggestion_rules = ["myapp.floor.my_rule"]  # (snapshot) -> list of finding dicts

# Process mining
# --------------
# Other apps add events to the process-mining event log. Each dotted path is called with
# (since, until) and returns an iterable of foames.foames_process_mining.eventlog.Event.
#
# foames_process_event_extractors = ["myapp.mining.job_events"]

# Scheduled Tasks
# ---------------

scheduler_events = {
	"all": [
		# Sends due postings to S/4HANA; does nothing unless the S/4HANA adapter is enabled.
		"foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox.process_outbox",
	],
	"cron": {
		"*/5 * * * *": ["foames.foames_mes.tasks.mark_stale_machines_unknown"],
	},
	"hourly": ["foames.foames_mes.tasks.run_suggestion_rules"],
	"daily": ["foames.foames_mes.tasks.compute_daily_oee"],
}

# Testing
# -------

before_tests = "foames.install.after_install"
