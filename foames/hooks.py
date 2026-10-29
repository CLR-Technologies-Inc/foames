app_name = "foames"
app_title = "FoaMES"
app_publisher = "CLR Technologies Inc."
app_description = "Process-engineered, ERP-agnostic MES on the Frappe framework"
app_email = ""
app_license = "bsd-3-clause"

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
]

# Installation
# ------------

# before_install = "foames.install.before_install"
# after_install = "foames.install.after_install"

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

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"daily": [
# 		"foames.tasks.daily"
# 	],
# }

# Testing
# -------

# before_tests = "foames.install.before_tests"
