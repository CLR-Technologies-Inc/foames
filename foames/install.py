# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe

ROLES = (
	"FoaMES Engineer",
	"FoaMES Operator",
	"FoaMES Supervisor",
	"FoaMES Maintenance",
	"FoaMES Quality",
	"FoaMES Integration",
)


def before_install():
	"""Create the FoaMES roles before the DocTypes that grant them permissions are synced."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	frappe.db.commit()


def after_install():
	before_install()
	from foames.foames_mes.doctype.andon_call_type.andon_call_type import create_default_call_types

	create_default_call_types()
	set_read_only_defaults(site_read_only=True)


def set_read_only_defaults(site_read_only: bool):
	"""Read-only mode for a new site: every connector reads only, and each write waits for an
	authorised operator's electronic sign-off until the plant approves the connector's writes."""
	values = {
		"read_only_mode": 1 if site_read_only else 0,
		"read_only_action": "Queue for sign-off",
		"new_connectors_read_only": 1,
		"sign_off_role": "FoaMES Supervisor",
		"require_second_person": 1,
		"gate_agent_suggestions": 0,
	}
	for field, value in values.items():
		frappe.db.set_single_value("FoaMES Settings", field, value)


def before_tests():
	"""The test site starts read-write, so the adapters' own tests exercise their send paths; the
	read-only tests turn the mode on for themselves."""
	after_install()
	frappe.db.set_single_value("FoaMES Settings", "read_only_mode", 0)
	frappe.db.set_single_value("FoaMES Settings", "new_connectors_read_only", 0)
	frappe.db.commit()
