# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""What the ERPNext adapter reads for each kernel reference type.

Everything here goes through `frappe.db`, so no ERPNext module is imported and the functions are
only called once the adapter has confirmed ERPNext is installed. The field names are ERPNext's
own; a missing column (an older or newer ERPNext) is tolerated field by field.
"""

import frappe

# Fields fetched from the parent record per kernel reference type.
DETAIL_FIELDS: dict[str, tuple[str, ...]] = {
	"Item": (
		"item_name",
		"item_group",
		"stock_uom",
		"disabled",
		"has_batch_no",
		"has_serial_no",
		"default_bom",
	),
	"Unit of Measure": ("uom_name", "must_be_whole_number", "enabled"),
	"Batch": ("item", "batch_qty", "expiry_date", "disabled"),
	"Serial Number": ("item_code", "warehouse", "status", "batch_no"),
	"Work Order": (
		"production_item",
		"item_name",
		"bom_no",
		"qty",
		"produced_qty",
		"material_transferred_for_manufacturing",
		"process_loss_qty",
		"status",
		"docstatus",
		"company",
		"wip_warehouse",
		"fg_warehouse",
		"source_warehouse",
		"skip_transfer",
		"stock_uom",
		"planned_start_date",
		"planned_end_date",
		"actual_start_date",
		"actual_end_date",
	),
	"Operation": ("workstation", "description", "batch_size", "total_operation_time"),
	"Location": ("warehouse_name", "company", "is_group", "parent_warehouse", "disabled"),
	"Stock Movement": (
		"purpose",
		"stock_entry_type",
		"work_order",
		"job_card",
		"fg_completed_qty",
		"from_warehouse",
		"to_warehouse",
		"posting_date",
		"posting_time",
		"docstatus",
		"remarks",
	),
	"Job Card": (
		"work_order",
		"operation",
		"workstation",
		"production_item",
		"for_quantity",
		"total_completed_qty",
		"total_time_in_mins",
		"process_loss_qty",
		"status",
		"docstatus",
		"sequence_id",
		"wip_warehouse",
		"expected_start_date",
		"expected_end_date",
		"actual_start_date",
		"actual_end_date",
	),
	"Bill of Materials": (
		"item",
		"item_name",
		"quantity",
		"uom",
		"is_active",
		"is_default",
		"docstatus",
		"with_operations",
		"routing",
		"company",
		"transfer_material_against",
	),
	"Routing": ("routing_name", "disabled"),
	"Workstation": (
		"workstation_name",
		"workstation_type",
		"status",
		"production_capacity",
		"warehouse",
		"disabled",
	),
}

# Child tables fetched per kernel reference type: key in `data` -> (child DocType, fields).
CHILD_TABLES: dict[str, dict[str, tuple[str, tuple[str, ...]]]] = {
	"Work Order": {
		"operations": (
			"Work Order Operation",
			("idx", "operation", "workstation", "sequence_id", "time_in_mins", "completed_qty", "status"),
		),
		"required_items": (
			"Work Order Item",
			("idx", "item_code", "source_warehouse", "required_qty", "transferred_qty", "consumed_qty"),
		),
	},
	"Bill of Materials": {
		"items": ("BOM Item", ("idx", "item_code", "qty", "uom", "stock_qty", "stock_uom", "operation")),
		"operations": ("BOM Operation", ("idx", "operation", "workstation", "sequence_id", "time_in_mins")),
	},
	"Routing": {
		"operations": ("BOM Operation", ("idx", "operation", "workstation", "sequence_id", "time_in_mins")),
	},
	"Job Card": {
		"time_logs": ("Job Card Time Log", ("idx", "from_time", "to_time", "time_in_mins", "completed_qty")),
	},
}


def get_details(
	doctype: str, reference_type: str, name: str, extra_fields: tuple[str, ...] = ()
) -> dict | None:
	"""The record's details as a plain dict, or None when it does not exist."""
	wanted = dict.fromkeys((*DETAIL_FIELDS.get(reference_type, ()), *extra_fields))
	fields = [f for f in wanted if _has_column(doctype, f)]
	values = frappe.db.get_value(doctype, name, ["name", *fields], as_dict=True)
	if not values:
		return None
	data = dict(values)
	data["doctype"] = doctype
	for key, (child_doctype, child_fields) in CHILD_TABLES.get(reference_type, {}).items():
		if not frappe.db.table_exists(child_doctype):
			continue
		child_fields = [f for f in child_fields if _has_column(child_doctype, f)]
		data[key] = frappe.get_all(
			child_doctype,
			filters={"parent": name, "parenttype": doctype},
			fields=child_fields,
			order_by="idx asc",
			parent_doctype=doctype,
		)
	return data


def _has_column(doctype: str, fieldname: str) -> bool:
	return fieldname == "name" or frappe.db.has_column(doctype, fieldname)


OPEN_WORK_ORDER_STATUSES = ("Not Started", "In Process", "Stock Reserved", "Stock Partially Reserved")
# A draft Job Card is open whatever its status reads (Open, Material Transferred, Work In Progress,
# On Hold ...). A submitted one is done, except a card that tracks semi-finished goods, which stays
# Work In Progress after submission until its output is manufactured.


def open_work_orders(workstation: str | None = None, limit: int = 100) -> list[dict]:
	"""Submitted Work Orders that are not started or in process, optionally those with an operation
	on the given workstation."""
	filters = {"docstatus": 1, "status": ("in", OPEN_WORK_ORDER_STATUSES)}
	if workstation:
		names = frappe.get_all(
			"Work Order Operation",
			filters={"workstation": workstation, "parenttype": "Work Order"},
			pluck="parent",
			distinct=True,
			parent_doctype="Work Order",
		)
		if not names:
			return []
		filters["name"] = ("in", names)
	return frappe.get_all(
		"Work Order",
		filters=filters,
		fields=[
			"name",
			"production_item",
			"item_name",
			"qty",
			"produced_qty",
			"material_transferred_for_manufacturing",
			"status",
			"planned_start_date",
			"planned_end_date",
		],
		order_by="planned_start_date asc, creation asc",
		limit_page_length=limit,
	)


def open_job_cards(workstations: list[str] | str | None = None, limit: int = 200) -> list[dict]:
	"""Job Cards still to be worked, optionally on the given workstations. `limit` 0 means all."""
	filters = {"docstatus": ("<", 2)}
	or_filters = [["docstatus", "=", 0], ["status", "=", "Work In Progress"]]
	if isinstance(workstations, str):
		workstations = [workstations]
	if workstations is not None:
		if not workstations:
			return []
		filters["workstation"] = ("in", workstations)
	return frappe.get_all(
		"Job Card",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"work_order",
			"operation",
			"workstation",
			"production_item",
			"for_quantity",
			"total_completed_qty",
			"status",
			"expected_start_date",
			"expected_end_date",
		],
		order_by="expected_start_date asc, creation asc",
		limit_page_length=limit,
	)
