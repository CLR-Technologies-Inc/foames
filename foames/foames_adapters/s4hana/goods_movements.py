# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Payloads for material documents (`A_MaterialDocumentHeader` with `to_MaterialDocumentItem` in
API_MATERIAL_DOCUMENT_SRV).

One material document posts one or more goods movements of the same kind, chosen by the header's
`GoodsMovementCode`:

| Code | Transaction it stands for | Typical movement types |
| --- | --- | --- |
| 01 | Goods receipt for purchase order | 101, 102 |
| 02 | Goods receipt for production order | 101 (receipt), 102 (reversal) |
| 03 | Goods issue | 261 (to order), 262, 201 (cost center) |
| 04 | Transfer posting | 311 (storage location), 301 (plant), 309 (material), 321 (QI to unrestricted) |
| 05 | Other goods receipt | 501, 531 (by-product), 561 (initial stock) |
| 06 | Reversal of a material document | the reversed document's types |

The outbox writes its idempotency marker into `MaterialDocumentHeaderText`, so do not set that
field. Field names follow SAP's released API; check them against your system's `$metadata`.

This module has no Frappe imports.
"""

from dataclasses import dataclass, field

from foames.foames_adapters.s4hana.values import clean, date_string, decimal_string, parse_date, parse_decimal

OPERATION = "Goods Movement"

GOODS_MOVEMENT_CODES = {
	"01": "Goods receipt for purchase order",
	"02": "Goods receipt for production order",
	"03": "Goods issue",
	"04": "Transfer posting",
	"05": "Other goods receipt",
	"06": "Reversal",
}

# Movement types FoaMES posts for an order, and the code each one goes with.
RECEIPT_FOR_ORDER = "101"
RECEIPT_FOR_ORDER_REVERSAL = "102"
ISSUE_TO_ORDER = "261"
ISSUE_TO_ORDER_REVERSAL = "262"
BY_PRODUCT_RECEIPT = "531"
TRANSFER_STORAGE_LOCATION = "311"
TRANSFER_PLANT = "301"
TRANSFER_QI_TO_UNRESTRICTED = "321"
TRANSFER_UNRESTRICTED_TO_BLOCKED = "344"
SCRAP = "551"

MOVEMENT_CODES = {
	RECEIPT_FOR_ORDER: "02",
	RECEIPT_FOR_ORDER_REVERSAL: "02",
	ISSUE_TO_ORDER: "03",
	ISSUE_TO_ORDER_REVERSAL: "03",
	SCRAP: "03",
	"201": "03",
	"202": "03",
	TRANSFER_STORAGE_LOCATION: "04",
	TRANSFER_PLANT: "04",
	"309": "04",
	TRANSFER_QI_TO_UNRESTRICTED: "04",
	TRANSFER_UNRESTRICTED_TO_BLOCKED: "04",
	"501": "05",
	BY_PRODUCT_RECEIPT: "05",
	"561": "05",
}


@dataclass
class Item:
	"""One line of a material document."""

	material: str
	plant: str
	quantity: object
	unit: str
	movement_type: str
	storage_location: str = ""
	batch: str = ""
	order: str = ""  # ManufacturingOrder, for 101/102/261/262/531
	order_item: str = ""
	reservation: str = ""
	reservation_item: str = ""
	is_completely_delivered: bool | None = None
	receiving_plant: str = ""  # for transfer postings
	receiving_storage_location: str = ""
	receiving_batch: str = ""
	receiving_material: str = ""
	stock_type: str = ""  # InventoryStockType: "" unrestricted, "2" quality inspection, "3" blocked
	receiving_stock_type: str = ""
	cost_center: str = ""
	gl_account: str = ""
	reason_code: str = ""
	text: str = ""
	manufacture_date: object = None
	shelf_life_expiration_date: object = None
	extra: dict = field(default_factory=dict)

	def fields(self) -> dict:
		if not self.material or not self.plant or not self.unit:
			raise ValueError("A material document item needs a material, a plant and a unit")
		if not self.movement_type:
			raise ValueError("A material document item needs a movement type")
		return clean(
			{
				"Material": self.material,
				"Plant": self.plant,
				"StorageLocation": self.storage_location or None,
				"Batch": self.batch or None,
				"GoodsMovementType": str(self.movement_type),
				"InventoryStockType": self.stock_type or None,
				"EntryUnit": self.unit,
				"QuantityInEntryUnit": decimal_string(self.quantity),
				"ManufacturingOrder": self.order or None,
				"ManufacturingOrderItem": self.order_item or None,
				"Reservation": self.reservation or None,
				"ReservationItem": self.reservation_item or None,
				"IsCompletelyDelivered": self.is_completely_delivered,
				"IssuingOrReceivingPlant": self.receiving_plant or None,
				"IssuingOrReceivingStorageLoc": self.receiving_storage_location or None,
				"IssgOrRcvgBatch": self.receiving_batch or None,
				"IssgOrRcvgMaterial": self.receiving_material or None,
				"IssuingOrReceivingStockType": self.receiving_stock_type or None,
				"CostCenter": self.cost_center or None,
				"GLAccount": self.gl_account or None,
				"GoodsMovementReasonCode": self.reason_code or None,
				"MaterialDocumentItemText": self.text[:50] if self.text else None,
				"ManufactureDate": date_string(self.manufacture_date) if self.manufacture_date else None,
				"ShelfLifeExpirationDate": date_string(self.shelf_life_expiration_date)
				if self.shelf_life_expiration_date
				else None,
				**self.extra,
			}
		)


def code_for(items: list[Item], code: str = "") -> str:
	"""The `GoodsMovementCode` for a list of items, from the given code or from the movement types."""
	if code:
		if code not in GOODS_MOVEMENT_CODES:
			raise ValueError(f"Goods movement code must be one of {', '.join(GOODS_MOVEMENT_CODES)}")
		return code
	codes = {MOVEMENT_CODES.get(str(item.movement_type)) for item in items}
	if None in codes:
		unknown = sorted({str(i.movement_type) for i in items if str(i.movement_type) not in MOVEMENT_CODES})
		raise ValueError(
			f"No goods movement code is known for movement type {', '.join(unknown)}; pass `code`"
		)
	if len(codes) != 1:
		raise ValueError("All items of one material document must share a goods movement code")
	return codes.pop()


def material_document(
	items: list[Item],
	*,
	posting_date=None,
	document_date=None,
	code: str = "",
	reference: str = "",
	extra: dict | None = None,
) -> dict:
	"""The `A_MaterialDocumentHeader` body with its items. Do not set `MaterialDocumentHeaderText`:
	the outbox writes its idempotency marker there."""
	if not items:
		raise ValueError("A material document needs at least one item")
	payload = clean(
		{
			"GoodsMovementCode": code_for(items, code),
			"PostingDate": date_string(posting_date) if posting_date else None,
			"DocumentDate": date_string(document_date or posting_date)
			if (document_date or posting_date)
			else None,
			"ReferenceDocument": reference[:16] if reference else None,
			"to_MaterialDocumentItem": [item.fields() for item in items],
		}
	)
	if extra:
		payload.update(clean(extra))
	payload.pop("MaterialDocumentHeaderText", None)
	return payload


def goods_receipt_for_order(
	order: str,
	material: str,
	plant: str,
	quantity,
	unit: str,
	*,
	storage_location: str = "",
	batch: str = "",
	order_item: str = "",
	posting_date=None,
	is_completely_delivered: bool | None = None,
	stock_type: str = "",
	manufacture_date=None,
	shelf_life_expiration_date=None,
	reversal: bool = False,
	**extra,
) -> dict:
	"""Receive the product of an order into stock (101), or take it back out (102 with `reversal`)."""
	if not order:
		raise ValueError("A goods receipt for an order needs the order")
	item = Item(
		material=material,
		plant=plant,
		quantity=quantity,
		unit=unit,
		movement_type=RECEIPT_FOR_ORDER_REVERSAL if reversal else RECEIPT_FOR_ORDER,
		storage_location=storage_location,
		batch=batch,
		order=order,
		order_item=order_item,
		is_completely_delivered=is_completely_delivered,
		stock_type=stock_type,
		manufacture_date=manufacture_date,
		shelf_life_expiration_date=shelf_life_expiration_date,
		extra=extra,
	)
	return material_document([item], posting_date=posting_date)


def goods_issue_to_order(
	order: str,
	components: list[Item | dict],
	*,
	posting_date=None,
	reversal: bool = False,
) -> dict:
	"""Consume components for an order (261), or return them (262 with `reversal`). Each component
	is an Item, or a dict with the Item's fields (material, plant, quantity, unit, batch ...). The
	order's reservation items (from the order's components) make S/4HANA settle the right
	requirement; without them it consumes against the order as unplanned."""
	if not order:
		raise ValueError("A goods issue to an order needs the order")
	movement_type = ISSUE_TO_ORDER_REVERSAL if reversal else ISSUE_TO_ORDER
	items = []
	for component in components:
		if isinstance(component, dict):
			component = Item(
				**{**component, "movement_type": component.get("movement_type") or movement_type}
			)
		if not component.movement_type:
			component.movement_type = movement_type
		component.order = component.order or order
		items.append(component)
	if not items:
		raise ValueError("A goods issue needs at least one component")
	return material_document(items, posting_date=posting_date)


def transfer_posting(
	material: str,
	plant: str,
	quantity,
	unit: str,
	*,
	from_storage_location: str = "",
	to_storage_location: str = "",
	to_plant: str = "",
	batch: str = "",
	to_batch: str = "",
	movement_type: str = TRANSFER_STORAGE_LOCATION,
	from_stock_type: str = "",
	to_stock_type: str = "",
	posting_date=None,
	reason_code: str = "",
	**extra,
) -> dict:
	"""Move stock between storage locations (311), plants (301) or stock types (321, 344).

	S/4HANA's one-step transfer posting takes the issuing side in the item's own fields and the
	receiving side in the `IssuingOrReceiving...` fields.
	"""
	if movement_type in (TRANSFER_STORAGE_LOCATION, TRANSFER_PLANT) and not (to_storage_location or to_plant):
		raise ValueError("A transfer posting needs a receiving storage location or plant")
	item = Item(
		material=material,
		plant=plant,
		quantity=quantity,
		unit=unit,
		movement_type=movement_type,
		storage_location=from_storage_location,
		batch=batch,
		stock_type=from_stock_type,
		receiving_plant=to_plant,
		receiving_storage_location=to_storage_location,
		receiving_batch=to_batch,
		receiving_stock_type=to_stock_type,
		reason_code=reason_code,
		extra=extra,
	)
	return material_document([item], posting_date=posting_date)


def scrap(
	material: str,
	plant: str,
	quantity,
	unit: str,
	*,
	storage_location: str = "",
	batch: str = "",
	cost_center: str = "",
	reason_code: str = "",
	posting_date=None,
	**extra,
) -> dict:
	"""Scrap stock from a storage location (551) against a cost center."""
	item = Item(
		material=material,
		plant=plant,
		quantity=quantity,
		unit=unit,
		movement_type=SCRAP,
		storage_location=storage_location,
		batch=batch,
		cost_center=cost_center,
		reason_code=reason_code,
		extra=extra,
	)
	return material_document([item], posting_date=posting_date)


def summarize_item(entity: dict) -> dict:
	"""The parts of an `A_MaterialDocumentItem` entity a screen or an agent usually wants."""
	return {
		"document": f"{entity.get('MaterialDocumentYear', '')}|{entity.get('MaterialDocument', '')}",
		"item": entity.get("MaterialDocumentItem", ""),
		"material": entity.get("Material", ""),
		"plant": entity.get("Plant", ""),
		"storage_location": entity.get("StorageLocation", ""),
		"batch": entity.get("Batch", ""),
		"movement_type": entity.get("GoodsMovementType", ""),
		"quantity": parse_decimal(entity.get("QuantityInEntryUnit")),
		"unit": entity.get("EntryUnit", ""),
		"quantity_in_base_unit": parse_decimal(entity.get("QuantityInBaseUnit")),
		"base_unit": entity.get("MaterialBaseUnit", ""),
		"order": entity.get("ManufacturingOrder", ""),
		"order_item": entity.get("ManufacturingOrderItem", ""),
		"reservation": entity.get("Reservation", ""),
		"reservation_item": entity.get("ReservationItem", ""),
		"debit_credit": entity.get("DebitCreditCode", ""),
		"cancelled": bool(entity.get("GoodsMovementIsCancelled")),
		"reverses": (
			f"{entity['ReversedMaterialDocumentYear']}|{entity['ReversedMaterialDocument']}"
			if entity.get("ReversedMaterialDocument")
			else ""
		),
		"posting_date": parse_date((entity.get("to_MaterialDocumentHeader") or {}).get("PostingDate")),
		"text": entity.get("MaterialDocumentItemText", ""),
	}
