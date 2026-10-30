# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""HTTP endpoints for S/4HANA.

S/4HANA sends IDocs to `receive_idoc` through an XML HTTP port (WE21) whose RFC destination (SM59)
points at /api/method/foames.foames_adapters.s4hana.api.receive_idoc and logs in with the API key and
secret of a FoaMES user that has the FoaMES Integration role (HTTP Basic, key as user, secret as
password).
"""

import frappe
from frappe import _

from foames.foames_adapters.s4hana import idoc as idoc_parser


@frappe.whitelist(methods=["POST"])
def receive_idoc():
	frappe.has_permission("S4HANA Inbound IDoc", "create", throw=True)
	if not frappe.db.get_single_value("S4HANA Settings", "enabled"):
		frappe.throw(_("The S/4HANA adapter is not enabled"), frappe.ValidationError)

	from foames.foames_adapters.doctype.s4hana_inbound_idoc.s4hana_inbound_idoc import receive

	try:
		idocs = idoc_parser.parse(frappe.request.get_data())
	except idoc_parser.IDocError as e:
		frappe.throw(str(e), frappe.ValidationError)

	received, duplicates = [], []
	for idoc in idocs:
		name, new = receive(idoc)
		(received if new else duplicates).append(name)
	return {"received": received, "duplicates": duplicates}
