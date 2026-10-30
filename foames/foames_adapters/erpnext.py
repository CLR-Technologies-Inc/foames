# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""ERPNext adapter.

ERPNext is optional. Nothing here is imported from ERPNext and no FoaMES DocType links to an
ERPNext DocType, so FoaMES installs and runs on a plain Frappe site. When ERPNext is installed on
the same site, references are resolved straight from its tables.
"""

import frappe

from foames.foames_adapters.base import ERPAdapter, ResolvedReference

# ERPNext DocType per kernel reference type, and the field used as a human-readable label.
ERPNEXT_DOCTYPES = {
	"Item": ("Item", "item_name"),
	"Unit of Measure": ("UOM", "uom_name"),
	"Batch": ("Batch", "batch_id"),
	"Serial Number": ("Serial No", "serial_no"),
	"Work Order": ("Work Order", "production_item"),
	"Operation": ("Operation", "description"),
	"Location": ("Warehouse", "warehouse_name"),
	"Stock Movement": ("Stock Entry", "stock_entry_type"),
	"Job Card": ("Job Card", "operation"),
	"Bill of Materials": ("BOM", "item"),
	"Routing": ("Routing", "routing_name"),
	"Workstation": ("Workstation", "workstation_name"),
}


class ERPNextAdapter(ERPAdapter):
	key = "ERPNext"
	label = "ERPNext"
	reference_map = {reference_type: doctype for reference_type, (doctype, _) in ERPNEXT_DOCTYPES.items()}  # noqa: RUF012

	def is_available(self) -> bool:
		return "erpnext" in frappe.get_installed_apps()

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		label_field = ERPNEXT_DOCTYPES[reference_type][1]
		values = frappe.db.get_value(erp_type, external_id, ["name", label_field], as_dict=True)
		if not values:
			return None
		return ResolvedReference(
			reference_type=reference_type,
			external_id=values.name,
			label=values.get(label_field) or values.name,
			data={"doctype": erp_type},
		)
