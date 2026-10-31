# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Scheduled kernel tasks."""

import frappe

from foames.foames_adapters import AdapterError, AdapterUnavailable, get_adapters


def refresh_external_references(limit: int = 500) -> dict:
	"""Look up External References that are Unverified or Missing in their ERP, oldest first.

	Every available adapter is tried; one that reports itself unavailable mid-run is left for the
	next run. Returns how many references were checked per ERP system.
	"""
	checked = {}
	for key, adapter in get_adapters().items():
		if not adapter.is_available():
			continue
		if key == "ERPNext" and not frappe.db.get_single_value(
			"ERPNext Adapter Settings", "refresh_references_daily"
		):
			continue
		names = frappe.get_all(
			"External Reference",
			filters={"erp_system": key, "status": ("in", ("Unverified", "Missing"))},
			order_by="last_resolved_on asc, creation asc",
			pluck="name",
			limit_page_length=limit,
		)
		count = 0
		for name in names:
			doc = frappe.get_doc("External Reference", name)
			try:
				doc.resolve_from_erp()
			except AdapterUnavailable:
				break
			except AdapterError:
				frappe.log_error(title=f"External Reference {name}: could not resolve")
				continue
			doc.flags.resolved = True
			doc.save(ignore_permissions=True)
			count += 1
		checked[key] = count
	return checked
