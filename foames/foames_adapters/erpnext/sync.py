# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""ERPNext document events that keep External References current.

Registered in hooks.py under `doc_events` for the ERPNext DocTypes the adapter maps. On a site
without ERPNext those DocTypes do not exist and the hooks never fire; the handlers also check
that the adapter is available, in case another app defines a DocType of the same name.

- A saved record refreshes the label of its reference and marks it Resolved.
- A deleted record marks its reference Missing. The reference itself stays, because FoaMES
  records point at it; a person decides what to do with them.
- A renamed record moves its reference to the new identifier.
"""

import frappe
from frappe.utils import now_datetime

from foames.foames_adapters.erpnext import (
	ADAPTER_KEY,
	ERPNEXT_DOCTYPES,
	REFERENCE_TYPES_BY_DOCTYPE,
	erpnext_installed,
)
from foames.foames_kernel.doctype.external_reference.external_reference import make_reference_key


def on_update(doc, method=None):
	"""Refresh the reference's label after the ERPNext record changes."""
	reference_type = _reference_type(doc)
	if not reference_type:
		return
	name = _reference_name(reference_type, doc.name)
	if not name:
		return
	label_field = ERPNEXT_DOCTYPES[reference_type][1]
	label = doc.get(label_field) or doc.name
	frappe.db.set_value(
		"External Reference",
		name,
		{"label": label, "status": "Resolved", "last_resolved_on": now_datetime()},
		update_modified=False,
	)


def on_trash(doc, method=None):
	"""An ERPNext record that is deleted leaves its reference behind as Missing."""
	reference_type = _reference_type(doc)
	if not reference_type:
		return
	name = _reference_name(reference_type, doc.name)
	if name:
		frappe.db.set_value(
			"External Reference",
			name,
			{"status": "Missing", "label": None, "last_resolved_on": now_datetime()},
			update_modified=False,
		)


def after_rename(doc, method=None, old=None, new=None, merge=False):
	"""Follow an ERPNext record to its new name."""
	reference_type = _reference_type(doc)
	if not reference_type or not old or not new:
		return
	name = _reference_name(reference_type, old)
	if not name:
		return
	target = _reference_name(reference_type, new)
	if target and target != name:
		# Both names were referenced; the old reference now points at a record that no longer exists.
		frappe.db.set_value(
			"External Reference", name, {"status": "Missing", "label": None}, update_modified=False
		)
		return
	frappe.db.set_value(
		"External Reference",
		name,
		{
			"external_id": new,
			"reference_key": make_reference_key(ADAPTER_KEY, reference_type, new),
			"last_resolved_on": now_datetime(),
		},
		update_modified=False,
	)


def _reference_type(doc) -> str | None:
	if not erpnext_installed():
		return None
	return REFERENCE_TYPES_BY_DOCTYPE.get(doc.doctype)


def _reference_name(reference_type: str, external_id: str) -> str | None:
	key = make_reference_key(ADAPTER_KEY, reference_type, external_id)
	return frappe.db.get_value("External Reference", {"reference_key": key}, "name")


# For hooks.py: every ERPNext DocType the adapter maps gets the same three handlers.
DOC_EVENTS = {
	doctype: {
		"on_update": "foames.foames_adapters.erpnext.sync.on_update",
		"on_update_after_submit": "foames.foames_adapters.erpnext.sync.on_update",
		"on_trash": "foames.foames_adapters.erpnext.sync.on_trash",
		"after_rename": "foames.foames_adapters.erpnext.sync.after_rename",
	}
	for doctype in REFERENCE_TYPES_BY_DOCTYPE
}
