# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Test fixtures for a site that has ERPNext installed: a company, a raw material with stock, a
finished good with a BOM and one operation, a workstation, and Work Orders on demand.

Everything is idempotent, so tests call `ensure_manufacturing_setup()` freely. Nothing here is
imported on a site without ERPNext; the tests skip first.
"""

import frappe
from frappe.utils import now_datetime, nowdate

COMPANY = "FoaMES Test Co"
ABBR = "FTC"
RAW_MATERIAL = "FOAMES-TEST-RM"
FINISHED_GOOD = "FOAMES-TEST-FG"
WORKSTATION = "FOAMES-TEST-WS1"
OPERATION = "FOAMES-TEST-OP1"
STORES = f"Stores - {ABBR}"
WIP = f"Work In Progress - {ABBR}"
FINISHED = f"Finished Goods - {ABBR}"


def ensure_manufacturing_setup() -> dict:
	ensure_company()
	ensure_items()
	ensure_workstation_and_operation()
	bom = ensure_bom()
	ensure_bom(with_operations=False)
	employee = ensure_employee()
	ensure_bom(with_operations=False, item=FINISHED_GOOD_BATCHED)
	ensure_bom(with_operations=False, item=FINISHED_GOOD_SERIAL)
	# Fixtures must outlive the per-test savepoint, so they are committed once.
	frappe.db.commit()  # nosemgrep
	return {
		"company": COMPANY,
		"bom": bom,
		"item": FINISHED_GOOD,
		"workstation": WORKSTATION,
		"employee": employee,
	}


EMPLOYEE_NAME = "FoaMES Test Operator"


def ensure_employee() -> str:
	"""The Employee ERPNext's Downtime Entry needs as its operator."""
	existing = frappe.db.get_value("Employee", {"employee_name": EMPLOYEE_NAME, "company": COMPANY}, "name")
	if existing:
		return existing
	if not frappe.db.exists("Gender", "Other"):
		frappe.get_doc({"doctype": "Gender", "gender": "Other"}).insert(ignore_permissions=True)
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "FoaMES Test",
				"last_name": "Operator",
				"company": COMPANY,
				"status": "Active",
				"gender": "Other",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def ensure_company():
	if frappe.db.exists("Company", COMPANY):
		return
	if not frappe.db.get_all("Company", limit=1):
		from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

		year = nowdate()[:4]
		setup_complete(
			{
				"language": "English",
				"email": "foames-test@example.com",
				"full_name": "FoaMES Test",
				"password": "foames-test",
				"country": "United States",
				"timezone": "America/New_York",
				"currency": "USD",
				"company_name": COMPANY,
				"company_abbr": ABBR,
				"chart_of_accounts": "Standard",
				"fy_start_date": f"{year}-01-01",
				"fy_end_date": f"{year}-12-31",
				"enable_telemetry": 0,
			}
		)
		for helper in ("enable_all_roles_and_domains", "set_defaults_for_tests"):
			try:
				frappe.get_attr(f"erpnext.setup.utils.{helper}")()
			except Exception:
				pass
	if not frappe.db.exists("Company", COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": COMPANY,
				"abbr": ABBR,
				"default_currency": "USD",
				"country": "United States",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "Standard",
				"enable_perpetual_inventory": 1,
			}
		).insert(ignore_permissions=True)
	frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
	# Scheduling Job Cards against workstation calendars is not what these tests are about.
	frappe.db.set_single_value("Manufacturing Settings", "disable_capacity_planning", 1)


FINISHED_GOOD_BATCHED = "FOAMES-TEST-FG-B"
FINISHED_GOOD_SERIAL = "FOAMES-TEST-FG-S"
BATCH_SERIES = "FOAMES-TB-.####"
ITEM_FLAGS = {
	FINISHED_GOOD_BATCHED: {"has_batch_no": 1, "create_new_batch": 1, "batch_number_series": BATCH_SERIES},
	FINISHED_GOOD_SERIAL: {"has_serial_no": 1, "serial_no_series": "FOAMES-TS-.####"},
}


def ensure_items():
	for item_code in (RAW_MATERIAL, FINISHED_GOOD, FINISHED_GOOD_BATCHED, FINISHED_GOOD_SERIAL):
		if frappe.db.exists("Item", item_code):
			continue
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name")
				or frappe.db.get_value("Item Group", {}, "name"),
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"valuation_rate": 10,
				"item_defaults": [{"company": COMPANY, "default_warehouse": STORES}],
				**ITEM_FLAGS.get(item_code, {}),
			}
		).insert(ignore_permissions=True)
	receive_raw_material(1000)


def receive_raw_material(qty: float):
	make_stock_entry = frappe.get_attr("erpnext.stock.doctype.stock_entry.stock_entry_utils.make_stock_entry")
	make_stock_entry(item_code=RAW_MATERIAL, qty=qty, to_warehouse=STORES, rate=10, company=COMPANY)


# ERPNext refuses a Job Card time log that overlaps another on the same workstation once the
# workstation's capacity is used up. Tests post logs for the same half hour, so the fixture has room.
WORKSTATION_CAPACITY = 100


INSPECTION_TEMPLATE = "FOAMES-TEST-QIT"
# (parameter, numeric, min, max, expected text)
INSPECTION_PARAMETERS = (
	("FOAMES-TEST-LENGTH", 1, 9.5, 10.5, None),
	("FOAMES-TEST-COLOUR", 0, None, None, "Blue"),
)


def ensure_inspection_template() -> str:
	"""A Quality Inspection Template with a numeric parameter (length 9.5 to 10.5) and a text one
	(colour Blue), hung on the test operation so its Job Cards inspect against it."""
	for parameter, *_rest in INSPECTION_PARAMETERS:
		if not frappe.db.exists("Quality Inspection Parameter", parameter):
			frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": parameter}).insert(
				ignore_permissions=True
			)
	if not frappe.db.exists("Quality Inspection Template", INSPECTION_TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "Quality Inspection Template",
				"quality_inspection_template_name": INSPECTION_TEMPLATE,
				"item_quality_inspection_parameter": [
					{
						"specification": parameter,
						"numeric": numeric,
						"min_value": low,
						"max_value": high,
						"value": expected,
					}
					for parameter, numeric, low, high, expected in INSPECTION_PARAMETERS
				],
			}
		).insert(ignore_permissions=True)
	return INSPECTION_TEMPLATE


def ensure_workstation_and_operation():
	if not frappe.db.exists("Workstation", WORKSTATION):
		frappe.get_doc(
			{
				"doctype": "Workstation",
				"workstation_name": WORKSTATION,
				"hour_rate": 50,
				"production_capacity": WORKSTATION_CAPACITY,
				"working_hours": [{"start_time": "06:00:00", "end_time": "22:00:00", "enabled": 1}],
			}
		).insert(ignore_permissions=True)
	elif frappe.db.get_value("Workstation", WORKSTATION, "production_capacity") != WORKSTATION_CAPACITY:
		frappe.db.set_value("Workstation", WORKSTATION, "production_capacity", WORKSTATION_CAPACITY)
	template = ensure_inspection_template()
	if not frappe.db.exists("Operation", OPERATION):
		frappe.get_doc(
			{
				"doctype": "Operation",
				"name": OPERATION,
				"workstation": WORKSTATION,
				"quality_inspection_template": template,
			}
		).insert(ignore_permissions=True)
	elif frappe.db.get_value("Operation", OPERATION, "quality_inspection_template") != template:
		frappe.db.set_value("Operation", OPERATION, "quality_inspection_template", template)


def ensure_bom(with_operations: bool = True, item: str = FINISHED_GOOD) -> str:
	"""The finished good's BOM: by default the one with a single operation (so a Work Order gets a
	Job Card), otherwise a plain one for stock-only tests. The batched and serialised finished
	goods get plain BOMs too."""
	existing = frappe.db.get_value(
		"BOM",
		{"item": item, "is_active": 1, "docstatus": 1, "with_operations": int(with_operations)},
		"name",
	)
	if existing:
		return existing
	operations = (
		[{"operation": OPERATION, "workstation": WORKSTATION, "time_in_mins": 10, "sequence_id": 1}]
		if with_operations
		else []
	)
	bom = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": item,
			"company": COMPANY,
			"quantity": 1,
			"is_active": 1,
			"is_default": int(with_operations or item != FINISHED_GOOD),
			"with_operations": int(with_operations),
			"rm_cost_as_per": "Valuation Rate",
			"operations": operations,
			"items": [
				{"item_code": RAW_MATERIAL, "qty": 1, "uom": "Nos", "rate": 10, "source_warehouse": STORES}
			],
		}
	)
	bom.insert(ignore_permissions=True)
	bom.submit()
	return bom.name


def make_work_order(
	qty: float = 5,
	submit: bool = True,
	skip_transfer: bool = False,
	operations: bool = True,
	item: str = FINISHED_GOOD,
):
	"""A submitted Work Order for the finished good. With `operations` it has one operation and
	therefore one Job Card, which must be completed before a Manufacture entry is accepted."""
	bom = ensure_bom(with_operations=operations, item=item)
	wo = frappe.new_doc("Work Order")
	wo.production_item = item
	wo.bom_no = bom
	wo.qty = qty
	wo.company = COMPANY
	wo.wip_warehouse = WIP
	wo.fg_warehouse = FINISHED
	wo.source_warehouse = STORES
	wo.skip_transfer = int(skip_transfer)
	wo.stock_uom = "Nos"
	wo.transfer_material_against = "Work Order"
	wo.planned_start_date = now_datetime()
	wo.get_items_and_operations_from_bom()
	for row in wo.required_items:
		row.source_warehouse = STORES
	wo.insert(ignore_permissions=True)
	if submit:
		wo.submit()
	return wo


def job_card_for(work_order: str) -> str | None:
	return frappe.db.get_value("Job Card", {"work_order": work_order, "docstatus": 0}, "name")
