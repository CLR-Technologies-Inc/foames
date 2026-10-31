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


after_install = before_install
