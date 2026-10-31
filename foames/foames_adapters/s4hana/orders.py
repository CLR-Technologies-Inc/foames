# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Reads of what the floor needs from S/4HANA: an order with its operations, components and
status; the confirmations and goods movements already posted for it; a routing with its
sequences and operations; a bill of material with its items; a work center.

Every function takes an ODataClient and returns plain dicts, with the raw entity under `raw` so
callers can reach fields the summaries leave out. Nothing here writes to S/4HANA or touches Frappe.
Entity sets and fields follow SAP's released APIs; check them against your system's `$metadata`.
"""

from foames.foames_adapters.s4hana import confirmations, goods_movements
from foames.foames_adapters.s4hana.odata import ODataClient, filter_expression
from foames.foames_adapters.s4hana.values import parse_date, parse_datetime, parse_decimal, parse_time

ORDER_SERVICE = "API_PRODUCTION_ORDER_2_SRV"
ORDER_SET = "A_ProductionOrder_2"
ORDER_EXPAND = (
	"to_ProductionOrderOperation,to_ProductionOrderComponent,to_ProductionOrderItem,to_ProductionOrderStatus"
)
PROCESS_ORDER_SERVICE = "API_PROCESS_ORDER_2_SRV"
PROCESS_ORDER_SET = "A_ProcessOrder_2"
PROCESS_ORDER_EXPAND = (
	"to_ProcessOrderOperation,to_ProcessOrderComponent,to_ProcessOrderItem,to_ProcessOrderStatus"
)

ROUTING_SERVICE = "API_PRODUCTION_ROUTING"
ROUTING_SET = "ProductionRoutingHeader"
ROUTING_EXPAND = "to_Sequence/to_Operation,to_MatlAssgmt"
ROUTING_MATERIAL_SET = "ProductionRoutingMatlAssgmt"

BOM_SERVICE = "API_BILL_OF_MATERIAL_SRV;v=0002"
BOM_SET = "MaterialBOM"
BOM_EXPAND = "to_BillOfMaterialItem"

WORK_CENTER_SERVICE = "API_WORK_CENTERS"
WORK_CENTER_SET = "A_WorkCenters"

# System statuses of an order that matter on the floor, by status code.
STATUS_CODES = {
	"I0001": "CRTD",
	"I0002": "REL",
	"I0009": "CNF",
	"I0010": "PCNF",
	"I0012": "DLV",
	"I0016": "PDLV",
	"I0045": "TECO",
	"I0046": "CLSD",
	"I0076": "DLFL",
	"I0013": "DLT",
	"I0043": "LKD",
}


def _results(data) -> list[dict]:
	if not data:
		return []
	if isinstance(data, dict):
		return data.get("results", []) if "results" in data else []
	return list(data)


# Orders


def production_order(client: ODataClient, order: str, process_order: bool = False) -> dict | None:
	"""One order with its operations, components, items and status, or None when it does not exist."""
	service, entity_set, expand = (
		(PROCESS_ORDER_SERVICE, PROCESS_ORDER_SET, PROCESS_ORDER_EXPAND)
		if process_order
		else (ORDER_SERVICE, ORDER_SET, ORDER_EXPAND)
	)
	entity = client.get_entity(service, entity_set, {"ManufacturingOrder": str(order)}, {"$expand": expand})
	if not entity:
		return None
	return summarize_order(entity)


def orders_for_material(
	client: ODataClient, material: str, plant: str = "", top: int = 50, released_only: bool = False
) -> list[dict]:
	"""Orders of a material (and plant), newest first, without their children."""
	filters = {"Material": material}
	if plant:
		filters["Plant"] = plant
	if released_only:
		filters["OrderIsReleased"] = "X"
	data = client.get(
		ORDER_SERVICE,
		ORDER_SET,
		{"$filter": filter_expression(filters), "$top": str(top), "$orderby": "ManufacturingOrder desc"},
	)
	return [summarize_order(entity) for entity in _results(data)]


def summarize_order(entity: dict) -> dict:
	# Order category 10 is a production order, 40 a process order; their children differ in name.
	is_process = str(entity.get("ManufacturingOrderCategory", "")) == "40" or any(
		key.startswith("to_ProcessOrder") for key in entity
	)
	prefix = "ProcessOrder" if is_process else "ProductionOrder"
	statuses = [
		{
			"code": s.get("StatusCode", ""),
			"short": s.get("StatusShortName", "") or STATUS_CODES.get(s.get("StatusCode", ""), ""),
			"name": s.get("StatusName", ""),
			"user_status": bool(s.get("IsUserStatus")),
		}
		for s in _results(entity.get(f"to_{prefix}Status"))
	]
	return {
		"order": entity.get("ManufacturingOrder", ""),
		"type": entity.get("ManufacturingOrderType", ""),
		"category": entity.get("ManufacturingOrderCategory", ""),
		"material": entity.get("Material", ""),
		"plant": entity.get("ProductionPlant", "") or entity.get("Plant", ""),
		"production_version": entity.get("ProductionVersion", ""),
		"mrp_controller": entity.get("MRPController", ""),
		"supervisor": entity.get("ProductionSupervisor", ""),
		"quantity": parse_decimal(entity.get("TotalQuantity")),
		"scrap_quantity": parse_decimal(entity.get("MfgOrderPlannedScrapQty")),
		"confirmed_yield": parse_decimal(entity.get("MfgOrderConfirmedYieldQty")),
		"unit": entity.get("ProductionUnit", ""),
		"planned_start": parse_datetime(
			_stamp(entity, "MfgOrderPlannedStartDate", "MfgOrderPlannedStartTime")
		),
		"planned_end": parse_datetime(_stamp(entity, "MfgOrderPlannedEndDate", "MfgOrderPlannedEndTime")),
		"scheduled_start": parse_datetime(
			_stamp(entity, "MfgOrderScheduledStartDate", "MfgOrderScheduledStartTime")
		),
		"scheduled_end": parse_datetime(
			_stamp(entity, "MfgOrderScheduledEndDate", "MfgOrderScheduledEndTime")
		),
		"actual_start": parse_datetime(_stamp(entity, "MfgOrderActualStartDate", "MfgOrderActualStartTime")),
		"actual_end": parse_datetime(_stamp(entity, "MfgOrderActualEndDate", "MfgOrderActualEndTime")),
		"created": bool(entity.get("OrderIsCreated")),
		"released": bool(entity.get("OrderIsReleased")),
		"confirmed": bool(entity.get("OrderIsConfirmed")),
		"partially_confirmed": bool(entity.get("OrderIsPartiallyConfirmed")),
		"delivered": bool(entity.get("OrderIsDelivered")),
		"partially_delivered": bool(entity.get("OrderIsPartiallyDelivered")),
		"technically_completed": bool(entity.get("OrderIsTechnicallyCompleted")),
		"closed": bool(entity.get("OrderIsClosed")),
		"marked_for_deletion": bool(entity.get("OrderIsMarkedForDeletion")),
		"statuses": statuses,
		"operations": [summarize_operation(o) for o in _results(entity.get(f"to_{prefix}Operation"))],
		"components": [summarize_component(c) for c in _results(entity.get(f"to_{prefix}Component"))],
		"items": [summarize_item(i) for i in _results(entity.get(f"to_{prefix}Item"))],
		"raw": _without_children(entity),
	}


def _stamp(entity: dict, date_field: str, time_field: str):
	day = parse_date(entity.get(date_field))
	if not day:
		return None
	clock = parse_time(entity.get(time_field))
	from datetime import datetime, time

	return datetime.combine(day, clock or time(0, 0))


def _without_children(entity: dict) -> dict:
	return {k: v for k, v in entity.items() if not k.startswith("to_") and k != "__metadata"}


def summarize_operation(entity: dict) -> dict:
	return {
		"sequence": entity.get("ManufacturingOrderSequence", ""),
		"operation": entity.get("ManufacturingOrderOperation", ""),
		"suboperation": entity.get("ManufacturingOrderSubOperation", ""),
		"text": entity.get("MfgOrderOperationText", "") or entity.get("OperationText", ""),
		"work_center": entity.get("WorkCenter", ""),
		"work_center_internal_id": entity.get("WorkCenterInternalID", ""),
		"plant": entity.get("ProductionPlant", "") or entity.get("Plant", ""),
		"control_key": entity.get("OperationControlProfile", ""),
		"quantity": parse_decimal(entity.get("OpPlannedTotalQuantity")),
		"confirmed_yield": parse_decimal(entity.get("OpTotalConfirmedYieldQty")),
		"confirmed_scrap": parse_decimal(entity.get("OpTotalConfirmedScrapQty")),
		"unit": entity.get("OperationUnit", ""),
		"planned_start": parse_datetime(_stamp(entity, "OpPlannedStartDate", "OpPlannedStartTime")),
		"planned_end": parse_datetime(_stamp(entity, "OpPlannedEndDate", "OpPlannedEndTime")),
		"actual_start": parse_datetime(_stamp(entity, "OpActualStartDate", "OpActualStartTime")),
		"actual_end": parse_datetime(_stamp(entity, "OpActualEndDate", "OpActualEndTime")),
		"is_confirmed": bool(entity.get("OperationIsConfirmed")) or bool(entity.get("OpIsConfirmed")),
		"is_partially_confirmed": bool(entity.get("OperationIsPartiallyConfirmed"))
		or bool(entity.get("OpIsPartiallyConfirmed")),
		"is_released": bool(entity.get("OperationIsReleased")) or bool(entity.get("OpIsReleased")),
		"internal_id": f"{entity.get('OrderInternalBillOfOperations', '')}|{entity.get('OrderIntBillOfOperationsItem', '')}",
		"raw": _without_children(entity),
	}


def summarize_component(entity: dict) -> dict:
	return {
		"reservation": entity.get("Reservation", ""),
		"reservation_item": entity.get("ReservationItem", ""),
		"material": entity.get("Material", ""),
		"plant": entity.get("Plant", ""),
		"storage_location": entity.get("StorageLocation", ""),
		"batch": entity.get("Batch", ""),
		"sequence": entity.get("ManufacturingOrderSequence", ""),
		"operation": entity.get("ManufacturingOrderOperation", ""),
		"required_quantity": parse_decimal(entity.get("RequiredQuantity")),
		"withdrawn_quantity": parse_decimal(entity.get("WithdrawnQuantity")),
		"unit": entity.get("BaseUnit", "") or entity.get("EntryUnit", ""),
		"requirement_date": parse_date(entity.get("MatlCompRequirementDate")),
		"is_backflushed": bool(entity.get("MatlCompIsBackflushed")) or bool(entity.get("IsBackflushed")),
		"is_bulk": bool(entity.get("MatlCompIsBulkMaterial")),
		"is_finally_issued": bool(entity.get("ReservationIsFinallyIssued"))
		or bool(entity.get("IsFinallyIssued")),
		"bom_item": entity.get("BillOfMaterialItemNumber", "") or entity.get("BOMItem", ""),
		"bom_item_category": entity.get("BOMItemCategory", ""),
		"raw": _without_children(entity),
	}


def summarize_item(entity: dict) -> dict:
	return {
		"item": entity.get("ManufacturingOrderItem", ""),
		"material": entity.get("Material", ""),
		"planned_quantity": parse_decimal(entity.get("MfgOrderItemPlannedTotalQty")),
		"planned_scrap": parse_decimal(entity.get("MfgOrderItemPlannedScrapQty")),
		"received_quantity": parse_decimal(entity.get("MfgOrderItemGoodsReceiptQty")),
		"deviation": parse_decimal(entity.get("MfgOrderItemActualDeviationQty")),
		"unit": entity.get("ProductionUnit", ""),
		"planned_delivery": parse_date(entity.get("MfgOrderItemPlndDeliveryDate")),
		"actual_delivery": parse_date(entity.get("MfgOrderItemActualDeliveryDate")),
		"is_completely_delivered": bool(entity.get("IsCompletelyDelivered")),
		"raw": _without_children(entity),
	}


# What was already posted for an order


def order_confirmations(
	client: ODataClient, order: str, process_order: bool = False, top: int = 200
) -> list[dict]:
	"""Confirmations posted for an order, oldest first, reversed ones included (`reversed` is set)."""
	service, entity_set = (
		("API_PROC_ORDER_CONFIRMATION_2_SRV", "ProcOrdConf2")
		if process_order
		else ("API_PROD_ORDER_CONFIRMATION_2_SRV", "ProdnOrdConf2")
	)
	data = client.get(
		service,
		entity_set,
		{
			"$filter": filter_expression({"OrderID": str(order)}),
			"$top": str(top),
			"$orderby": "ConfirmationGroup,ConfirmationCount",
		},
	)
	return [confirmations.summarize(entity) for entity in _results(data)]


def order_goods_movements(client: ODataClient, order: str, top: int = 500) -> list[dict]:
	"""Material document items posted for an order: receipts, consumptions and their reversals."""
	data = client.get(
		"API_MATERIAL_DOCUMENT_SRV",
		"A_MaterialDocumentItem",
		{
			"$filter": filter_expression({"ManufacturingOrder": str(order)}),
			"$top": str(top),
			"$expand": "to_MaterialDocumentHeader",
			"$orderby": "MaterialDocumentYear,MaterialDocument,MaterialDocumentItem",
		},
	)
	return [goods_movements.summarize_item(entity) for entity in _results(data)]


def order_balance(client: ODataClient, order: str) -> dict:
	"""Receipts and consumptions of an order, net of reversals, by material and batch."""
	receipts: dict[tuple[str, str], dict] = {}
	consumptions: dict[tuple[str, str], dict] = {}
	for movement in order_goods_movements(client, order):
		if movement["cancelled"]:
			continue
		bucket = receipts if movement["movement_type"] in ("101", "102", "531", "532") else consumptions
		sign = 1 if movement["movement_type"] in ("101", "531", "261", "201") else -1
		if movement["reverses"]:
			sign = -1
		key = (movement["material"], movement["batch"])
		entry = bucket.setdefault(
			key,
			{
				"material": movement["material"],
				"batch": movement["batch"],
				"quantity": 0,
				"unit": movement["unit"],
			},
		)
		entry["quantity"] += sign * movement["quantity"]
	return {
		"order": str(order),
		"receipts": list(receipts.values()),
		"consumptions": list(consumptions.values()),
	}


# Master data


def routing(client: ODataClient, group: str, counter: str, version: str = "") -> dict | None:
	"""A routing with its sequences, operations and material assignments."""
	entity = client.get_entity(
		ROUTING_SERVICE,
		ROUTING_SET,
		{
			"ProductionRoutingGroup": group,
			"ProductionRouting": counter,
			"ProductionRoutingInternalVers": version,
		},
		{"$expand": ROUTING_EXPAND},
	)
	if not entity:
		return None
	return summarize_routing(entity)


def routings_for_material(client: ODataClient, material: str, plant: str, top: int = 20) -> list[dict]:
	"""The routings assigned to a material in a plant (group and counter), without their operations."""
	data = client.get(
		ROUTING_SERVICE,
		ROUTING_MATERIAL_SET,
		{"$filter": filter_expression({"Product": material, "Plant": plant}), "$top": str(top)},
	)
	return [
		{
			"group": a.get("ProductionRoutingGroup", ""),
			"counter": a.get("ProductionRouting", ""),
			"version": a.get("ProductionRoutingInternalVers", ""),
			"material": a.get("Product", ""),
			"plant": a.get("Plant", ""),
			"valid_from": parse_date(a.get("ValidityStartDate")),
			"valid_to": parse_date(a.get("ValidityEndDate")),
			"raw": _without_children(a),
		}
		for a in _results(data)
	]


def summarize_routing(entity: dict) -> dict:
	sequences = []
	for sequence in _results(entity.get("to_Sequence")):
		sequences.append(
			{
				"sequence": sequence.get("ProductionRoutingSequence", ""),
				"category": sequence.get("SequenceCategory", "")
				or sequence.get("BillOfOperationsSequenceCategory", ""),
				"text": sequence.get("SequenceText", "") or sequence.get("BillOfOperationsSequenceText", ""),
				"operations": [
					summarize_routing_operation(o) for o in _results(sequence.get("to_Operation"))
				],
				"raw": _without_children(sequence),
			}
		)
	return {
		"group": entity.get("ProductionRoutingGroup", ""),
		"counter": entity.get("ProductionRouting", ""),
		"version": entity.get("ProductionRoutingInternalVers", ""),
		"description": entity.get("BillOfOperationsDesc", ""),
		"plant": entity.get("Plant", ""),
		"usage": entity.get("BillOfOperationsUsage", ""),
		"status": entity.get("BillOfOperationsStatus", ""),
		"unit": entity.get("BillOfOperationsUnit", ""),
		"lot_size_from": parse_decimal(entity.get("MinimumLotSizeQuantity")),
		"lot_size_to": parse_decimal(entity.get("MaximumLotSizeQuantity")),
		"valid_from": parse_date(entity.get("ValidityStartDate")),
		"valid_to": parse_date(entity.get("ValidityEndDate")),
		"marked_for_deletion": bool(entity.get("IsMarkedForDeletion")),
		"materials": [
			{"material": a.get("Product", ""), "plant": a.get("Plant", "")}
			for a in _results(entity.get("to_MatlAssgmt"))
		],
		"sequences": sequences,
		"operations": [op for s in sequences for op in s["operations"]],
		"raw": _without_children(entity),
	}


def summarize_routing_operation(entity: dict) -> dict:
	activities = []
	for n in range(1, confirmations.MAX_ACTIVITIES + 1):
		quantity = entity.get(f"OpStandardWorkQuantity{n}")
		if quantity in (None, "", "0", "0.000"):
			continue
		activities.append(
			{
				"position": n,
				"quantity": parse_decimal(quantity),
				"unit": entity.get(f"OpStandardWorkQuantityUnit{n}", ""),
				"parameter": entity.get(f"StandardWorkFormulaParamValue{n}", "")
				or entity.get(f"StandardWorkQuantityParam{n}", ""),
			}
		)
	return {
		"operation": entity.get("ProductionRoutingOperation", "") or entity.get("Operation", ""),
		"text": entity.get("OperationText", ""),
		"work_center": entity.get("WorkCenter", ""),
		"plant": entity.get("Plant", ""),
		"control_key": entity.get("OperationControlProfile", ""),
		"base_quantity": parse_decimal(entity.get("OperationReferenceQuantity")),
		"unit": entity.get("OperationUnit", ""),
		"standard_value_key": entity.get("OpStandardWorkQtyKey", "") or entity.get("StandardValueKey", ""),
		"activities": activities,
		"raw": _without_children(entity),
	}


def bill_of_material(
	client: ODataClient, bom: str, variant: str = "1", category: str = "M", version: str = ""
) -> dict | None:
	"""A material BOM with its items."""
	entity = client.get_entity(
		BOM_SERVICE,
		BOM_SET,
		{
			"BillOfMaterial": bom,
			"BillOfMaterialCategory": category,
			"BillOfMaterialVariant": variant,
			"BillOfMaterialVersion": version,
		},
		{"$expand": BOM_EXPAND},
	)
	if not entity:
		return None
	return summarize_bom(entity)


def boms_for_material(client: ODataClient, material: str, plant: str, top: int = 20) -> list[dict]:
	"""The BOMs of a material in a plant, without their items."""
	data = client.get(
		BOM_SERVICE,
		BOM_SET,
		{"$filter": filter_expression({"Material": material, "Plant": plant}), "$top": str(top)},
	)
	return [summarize_bom(entity) for entity in _results(data)]


def summarize_bom(entity: dict) -> dict:
	return {
		"bom": entity.get("BillOfMaterial", ""),
		"category": entity.get("BillOfMaterialCategory", ""),
		"variant": entity.get("BillOfMaterialVariant", ""),
		"version": entity.get("BillOfMaterialVersion", ""),
		"material": entity.get("Material", ""),
		"plant": entity.get("Plant", ""),
		"usage": entity.get("BillOfMaterialVariantUsage", ""),
		"status": entity.get("BillOfMaterialStatus", ""),
		"text": entity.get("BOMHeaderText", ""),
		"base_quantity": parse_decimal(entity.get("BOMHeaderQuantityInBaseUnit")),
		"unit": entity.get("BOMHeaderBaseUnit", ""),
		"valid_from": parse_date(entity.get("HeaderValidityStartDate")),
		"valid_to": parse_date(entity.get("HeaderValidityEndDate")),
		"marked_for_deletion": bool(entity.get("IsMarkedForDeletion")),
		"items": [
			{
				"item": i.get("BillOfMaterialItemNumber", ""),
				"node": i.get("BillOfMaterialItemNodeNumber", ""),
				"category": i.get("BillOfMaterialItemCategory", ""),
				"component": i.get("BillOfMaterialComponent", ""),
				"description": i.get("ComponentDescription", ""),
				"quantity": parse_decimal(i.get("BillOfMaterialItemQuantity")),
				"unit": i.get("BillOfMaterialItemUnit", ""),
				"scrap_percent": parse_decimal(i.get("ComponentScrapInPercent")),
				"is_backflushed": bool(i.get("IsBackflushed")) or bool(i.get("BOMItemIsBackflushed")),
				"is_bulk": bool(i.get("IsBulkMaterial")),
				"valid_from": parse_date(i.get("ValidityStartDate")),
				"valid_to": parse_date(i.get("ValidityEndDate")),
				"raw": _without_children(i),
			}
			for i in _results(entity.get("to_BillOfMaterialItem"))
		],
		"raw": _without_children(entity),
	}


def work_center(client: ODataClient, internal_id: str, type_code: str = "A") -> dict | None:
	entity = client.get_entity(
		WORK_CENTER_SERVICE,
		WORK_CENTER_SET,
		{"WorkCenterInternalID": internal_id, "WorkCenterTypeCode": type_code},
	)
	if not entity:
		return None
	return summarize_work_center(entity)


def work_centers(client: ODataClient, plant: str, top: int = 200) -> list[dict]:
	data = client.get(
		WORK_CENTER_SERVICE,
		WORK_CENTER_SET,
		{"$filter": filter_expression({"Plant": plant}), "$top": str(top), "$orderby": "WorkCenter"},
	)
	return [summarize_work_center(entity) for entity in _results(data)]


def summarize_work_center(entity: dict) -> dict:
	return {
		"work_center": entity.get("WorkCenter", ""),
		"internal_id": entity.get("WorkCenterInternalID", ""),
		"type_code": entity.get("WorkCenterTypeCode", ""),
		"plant": entity.get("Plant", ""),
		"description": entity.get("WorkCenterDesc", "") or entity.get("WorkCenterText", ""),
		"category": entity.get("WorkCenterCategoryCode", ""),
		"usage": entity.get("WorkCenterUsage", ""),
		"responsible": entity.get("WorkCenterResponsible", ""),
		"capacity_category": entity.get("CapacityCategoryCode", ""),
		"standard_value_key": entity.get("WorkCenterStdValueKey", "") or entity.get("StandardValueKey", ""),
		"valid_from": parse_date(entity.get("ValidityStartDate")),
		"valid_to": parse_date(entity.get("ValidityEndDate")),
		"raw": _without_children(entity),
	}
