# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Payloads for production and process order confirmations (`ProdnOrdConf2` in
API_PROD_ORDER_CONFIRMATION_2_SRV and `ProcOrdConf2` in API_PROC_ORDER_CONFIRMATION_2_SRV).

A confirmation reports, for one operation of an order, the yield, scrap and rework quantities, the
activities (machine time, labour time ... up to six), the execution times, who did the work and
whether the operation is finished. The goods movements that belong to the confirmation can ride
along as `to_ProdnOrdConfMatlDocItm` items. S/4HANA treats that list as the complete set: as soon
as one item is given, nothing is determined automatically any more, so a caller gives either no
items (S/4HANA backflushes and receives according to the order) or every movement, backflushed
components and goods receipt included.

The builders here only shape the payload. They do not talk to S/4HANA: the S4HANA Outbox sends what
they build, with the idempotency marker written into `ConfirmationText`. Field names follow SAP's
released API; check them against your system's `$metadata` (the names are the same for production
and process orders).

This module has no Frappe imports.
"""

from dataclasses import dataclass, field

from foames.foames_adapters.s4hana.values import (
	clean,
	date_string,
	datetime_string,
	decimal_string,
	time_string,
)

PRODUCTION = "Production Order Confirmation"
PROCESS = "Process Order Confirmation"

# Positions of the activities in the operation's standard value key, 1 to 6.
MAX_ACTIVITIES = 6

# `FinalConfirmationType`: how S/4HANA treats the operation after this confirmation.
FINAL_CONFIRMATION_TYPES = {
	"": "Automatic: final when the confirmed quantity reaches the operation quantity",
	"X": "Final confirmation",
	"P": "Partial confirmation",
}

# The fields of `ProdnOrdConf2` a confirmation may carry, grouped the way the builders fill them.
HEADER_FIELDS = ("OrderID", "Sequence", "OrderOperation", "OrderSuboperation", "Plant", "WorkCenter")
QUANTITY_FIELDS = (
	"ConfirmationYieldQuantity",
	"ConfirmationScrapQuantity",
	"ConfirmationReworkQuantity",
	"ConfirmationUnit",
	"VarianceReasonCode",
)
TIME_FIELDS = (
	"ConfirmedExecutionStartDate",
	"ConfirmedExecutionStartTime",
	"ConfirmedSetupEndDate",
	"ConfirmedSetupEndTime",
	"ConfirmedProcessingStartDate",
	"ConfirmedProcessingStartTime",
	"ConfirmedProcessingEndDate",
	"ConfirmedProcessingEndTime",
	"ConfirmedTeardownStartDate",
	"ConfirmedTeardownStartTime",
	"ConfirmedExecutionEndDate",
	"ConfirmedExecutionEndTime",
)


@dataclass
class Activity:
	"""One confirmed activity, in the position its standard value has on the operation
	(1 = setup, 2 = machine, 3 = labour in SAP's default standard value key SAP1)."""

	position: int
	quantity: object
	unit: str = ""
	no_further_expected: bool | None = None

	def fields(self) -> dict:
		if not 1 <= int(self.position) <= MAX_ACTIVITIES:
			raise ValueError(f"Activity position must be 1 to {MAX_ACTIVITIES}, not {self.position}")
		n = int(self.position)
		return clean(
			{
				f"OpConfirmedWorkQuantity{n}": decimal_string(self.quantity),
				f"OpWorkQuantityUnit{n}": self.unit or None,
				f"NoFurtherOpWorkQuantity{n}IsExpd": self.no_further_expected,
			}
		)


@dataclass
class GoodsMovementItem:
	"""A component consumption or product receipt posted together with the confirmation.

	Giving any item switches S/4HANA's automatic determination off for this confirmation, so the
	items must then cover every movement: all backflushed components, the goods receipt of the
	product and any by-products. Use it to set batches and storage locations S/4HANA cannot
	determine itself; leave the list empty to let the order's settings decide."""

	material: str
	plant: str
	quantity: object
	unit: str
	movement_type: str  # 261 consumption, 262 reversal, 101 receipt, 531 by-product ...
	storage_location: str = ""
	batch: str = ""
	reservation: str = ""
	reservation_item: str = ""
	order_item: str = ""
	is_completely_delivered: bool | None = None
	extra: dict = field(default_factory=dict)

	def fields(self) -> dict:
		if not self.material or not self.plant or not self.unit:
			raise ValueError("A goods movement item needs a material, a plant and a unit")
		return clean(
			{
				"Material": self.material,
				"Plant": self.plant,
				"StorageLocation": self.storage_location or None,
				"Batch": self.batch or None,
				"GoodsMovementType": str(self.movement_type),
				"QuantityInEntryUnit": decimal_string(self.quantity),
				"EntryUnit": self.unit,
				"Reservation": self.reservation or None,
				"ReservationItem": self.reservation_item or None,
				"ManufacturingOrderItem": self.order_item or None,
				"IsCompletelyDelivered": self.is_completely_delivered,
				**self.extra,
			}
		)


@dataclass
class ExecutionTimes:
	"""When the work happened, as datetimes. Setup end, processing start/end and teardown start are
	optional; S/4HANA derives the activities from them when the operation is set up for that."""

	start: object = None
	end: object = None
	setup_end: object = None
	processing_start: object = None
	processing_end: object = None
	teardown_start: object = None

	def fields(self) -> dict:
		pairs = {
			"ConfirmedExecutionStart": self.start,
			"ConfirmedSetupEnd": self.setup_end,
			"ConfirmedProcessingStart": self.processing_start,
			"ConfirmedProcessingEnd": self.processing_end,
			"ConfirmedTeardownStart": self.teardown_start,
			"ConfirmedExecutionEnd": self.end,
		}
		fields = {}
		for prefix, value in pairs.items():
			if value is None or value == "":
				continue
			stamp = datetime_string(value)
			fields[prefix + "Date"] = date_string(stamp[:10])
			fields[prefix + "Time"] = time_string(stamp[11:19])
		return fields


def confirmation(
	order: str,
	operation: str,
	yield_quantity=None,
	unit: str = "",
	*,
	scrap_quantity=None,
	rework_quantity=None,
	sequence: str = "0",
	suboperation: str = "",
	plant: str = "",
	work_center: str = "",
	posting_date=None,
	final: bool | None = None,
	final_confirmation_type: str | None = None,
	clear_open_reservations: bool | None = None,
	personnel: str = "",
	variance_reason: str = "",
	activities: list[Activity] | None = None,
	times: ExecutionTimes | None = None,
	goods_movements: list[GoodsMovementItem] | None = None,
	no_goods_movements: bool | None = None,
	extra: dict | None = None,
) -> dict:
	"""The `ProdnOrdConf2` body for one operation confirmation.

	`order` and `operation` are required. At least one of a yield, scrap or rework quantity, an
	activity, execution times or `final` must be given, otherwise there is nothing to confirm.
	`unit` is required with a quantity. Do not set `ConfirmationText`: the outbox writes its
	idempotency marker there.
	"""
	if not order or not operation:
		raise ValueError("A confirmation needs an order and an operation")
	quantities = [q for q in (yield_quantity, scrap_quantity, rework_quantity) if q not in (None, "")]
	if quantities and not unit:
		raise ValueError("A confirmed quantity needs a unit")
	if final_confirmation_type is not None and final_confirmation_type not in FINAL_CONFIRMATION_TYPES:
		raise ValueError(
			f"Final confirmation type must be one of {', '.join(repr(k) for k in FINAL_CONFIRMATION_TYPES)}"
		)
	finishes = final is not None or final_confirmation_type not in (None, "")
	if not quantities and not activities and not times and not finishes and not goods_movements:
		raise ValueError("A confirmation needs a quantity, an activity, execution times or the final flag")

	payload = clean(
		{
			"OrderID": str(order),
			"Sequence": str(sequence) if sequence not in (None, "") else "0",
			"OrderOperation": str(operation),
			"OrderSuboperation": suboperation or None,
			"Plant": plant or None,
			"WorkCenter": work_center or None,
			"ConfirmationYieldQuantity": decimal_string(yield_quantity)
			if yield_quantity not in (None, "")
			else None,
			"ConfirmationScrapQuantity": decimal_string(scrap_quantity)
			if scrap_quantity not in (None, "")
			else None,
			"ConfirmationReworkQuantity": decimal_string(rework_quantity)
			if rework_quantity not in (None, "")
			else None,
			"ConfirmationUnit": unit or None,
			"VarianceReasonCode": variance_reason or None,
			"PostingDate": date_string(posting_date) if posting_date else None,
			"IsFinalConfirmation": final,
			"FinalConfirmationType": final_confirmation_type,
			"OpenReservationsIsCleared": clear_open_reservations,
			"Personnel": personnel or None,
			"APIConfHasNoGoodsMovements": no_goods_movements,
		}
	)
	positions = set()
	for activity in activities or []:
		if activity.position in positions:
			raise ValueError(f"Activity position {activity.position} is given twice")
		positions.add(activity.position)
		payload.update(activity.fields())
	if times:
		payload.update(times.fields())
	if goods_movements:
		# Every item names the order; S/4HANA requires it on the child and does not inherit it.
		payload["to_ProdnOrdConfMatlDocItm"] = [
			{"OrderID": str(order), **item.fields()} for item in goods_movements
		]
	if extra:
		payload.update(clean(extra))
	payload.pop("ConfirmationText", None)
	return payload


def summarize(entity: dict) -> dict:
	"""The parts of a `ProdnOrdConf2` entity a screen or an agent usually wants."""
	from foames.foames_adapters.s4hana.values import parse_date, parse_decimal

	return {
		"confirmation": f"{entity.get('ConfirmationGroup', '')}|{entity.get('ConfirmationCount', '')}",
		"confirmation_group": entity.get("ConfirmationGroup", ""),
		"confirmation_count": entity.get("ConfirmationCount", ""),
		"order": entity.get("OrderID", ""),
		"sequence": entity.get("Sequence", ""),
		"operation": entity.get("OrderOperation", ""),
		"suboperation": entity.get("OrderSuboperation", ""),
		"work_center": entity.get("WorkCenter", ""),
		"plant": entity.get("Plant", ""),
		"personnel": entity.get("Personnel", ""),
		"yield": parse_decimal(entity.get("ConfirmationYieldQuantity")),
		"scrap": parse_decimal(entity.get("ConfirmationScrapQuantity")),
		"rework": parse_decimal(entity.get("ConfirmationReworkQuantity")),
		"unit": entity.get("ConfirmationUnit", ""),
		"posting_date": parse_date(entity.get("PostingDate")),
		"final": bool(entity.get("IsFinalConfirmation")),
		"reversed": bool(entity.get("IsReversed")),
		"is_reversal": bool(entity.get("IsReversal")),
		"text": entity.get("ConfirmationText", ""),
		"activities": [
			{
				"position": n,
				"quantity": parse_decimal(entity.get(f"OpConfirmedWorkQuantity{n}")),
				"unit": entity.get(f"OpWorkQuantityUnit{n}", ""),
			}
			for n in range(1, MAX_ACTIVITIES + 1)
			if entity.get(f"OpConfirmedWorkQuantity{n}") not in (None, "", "0", "0.000")
		],
	}
