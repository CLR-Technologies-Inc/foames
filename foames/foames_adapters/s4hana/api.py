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


# Reads and postings for operator screens, agents and integrations
# ---------------------------------------------------------------
#
# Reads need the FoaMES Operator, Engineer, Quality or Integration role (or System Manager) and an
# enabled adapter. Queuing a posting needs create permission on S4HANA Outbox and a POST request
# (Frappe commits writes made in a POST, not in a GET); the scheduler then sends it with the
# adapter's own S/4HANA credentials, so nothing is posted synchronously and a repeated call with
# the same idempotency key returns the same outbox record.

import json as _json

from foames.foames_adapters.s4hana import actions, confirmations, goods_movements, orders, outbox
from foames.foames_adapters.s4hana.odata import ODataError

READ_ROLES = ("System Manager", "FoaMES Engineer", "FoaMES Operator", "FoaMES Integration", "FoaMES Quality")


def _settings():
	from foames.foames_adapters.doctype.s4hana_settings.s4hana_settings import get_settings

	settings = get_settings()
	if not settings.enabled or not settings.base_url:
		frappe.throw(_("The S/4HANA adapter is not enabled"), frappe.ValidationError)
	return settings


def _client():
	if not set(frappe.get_roles()) & set(READ_ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return _settings().client()


def _read(call, *args, **kwargs):
	try:
		return call(_client(), *args, **kwargs)
	except ODataError as e:
		frappe.throw(str(e), title=_("S/4HANA"))


def _loads(value, what: str):
	if value is None or value == "":
		return None
	if isinstance(value, str):
		try:
			return _json.loads(value)
		except ValueError:
			frappe.throw(_("{0} is not valid JSON").format(what))
	return value


def _enqueue(
	operation: str,
	payload: dict,
	idempotency_key: str,
	sequence_group: str | None,
	reference_doctype=None,
	reference_name=None,
) -> dict:
	frappe.has_permission("S4HANA Outbox", "create", throw=True)
	_settings()
	if not idempotency_key:
		frappe.throw(_("An idempotency key is required"))
	try:
		outbox.prepare(outbox.operation(operation), payload, idempotency_key)
	except ValueError as e:
		frappe.throw(str(e))
	from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue

	name = enqueue(
		operation,
		payload,
		idempotency_key,
		sequence_group=sequence_group,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)
	return {"outbox": name, "operation": operation, "payload": payload}


@frappe.whitelist()
def get_operations() -> list[dict]:
	"""The outbox operations, with what each payload needs."""
	result = []
	for op in outbox.OPERATIONS.values():
		result.append(
			{
				"operation": op.label,
				"kind": "create",
				"service": op.service,
				"entity_set": op.entity_set,
				"required": list(op.lookup_fields),
				"marker_field": op.marker_field,
				"reference_type": op.reference_type,
			}
		)
	for action in actions.ACTIONS.values():
		result.append(
			{
				"operation": action.label,
				"kind": "function",
				"service": action.service,
				"function": action.function,
				"required": list(action.required),
				"optional": list(action.optional),
				"reference_type": action.reference_type,
			}
		)
	return result


# Reads


@frappe.whitelist()
def get_production_order(order: str, process_order: bool = False) -> dict:
	"""An order with its operations, components, items and status."""
	result = _read(orders.production_order, order, process_order=bool(int(process_order or 0)))
	if not result:
		frappe.throw(_("Order {0} does not exist in S/4HANA").format(order), frappe.DoesNotExistError)
	return result


@frappe.whitelist()
def get_orders_for_material(
	material: str, plant: str = "", top: int = 50, released_only: bool = False
) -> list[dict]:
	return _read(
		orders.orders_for_material,
		material,
		plant=plant,
		top=int(top),
		released_only=bool(int(released_only or 0)),
	)


@frappe.whitelist()
def get_order_confirmations(order: str, process_order: bool = False) -> list[dict]:
	return _read(orders.order_confirmations, order, process_order=bool(int(process_order or 0)))


@frappe.whitelist()
def get_order_goods_movements(order: str) -> list[dict]:
	return _read(orders.order_goods_movements, order)


@frappe.whitelist()
def get_order_balance(order: str) -> dict:
	"""Receipts and consumptions of an order, net of reversals, by material and batch."""
	return _read(orders.order_balance, order)


@frappe.whitelist()
def get_routing(group: str, counter: str, version: str = "") -> dict:
	result = _read(orders.routing, group, counter, version)
	if not result:
		frappe.throw(
			_("Routing {0}/{1} does not exist in S/4HANA").format(group, counter), frappe.DoesNotExistError
		)
	return result


@frappe.whitelist()
def get_routings_for_material(material: str, plant: str) -> list[dict]:
	return _read(orders.routings_for_material, material, plant)


@frappe.whitelist()
def get_bill_of_material(
	bom: str,
	material: str,
	plant: str,
	variant: str = "1",
	category: str = "M",
	version: str = "",
	change_document: str = "",
) -> dict:
	result = _read(orders.bill_of_material, bom, material, plant, variant, category, version, change_document)
	if not result:
		frappe.throw(_("BOM {0} does not exist in S/4HANA").format(bom), frappe.DoesNotExistError)
	return result


@frappe.whitelist()
def get_boms_for_material(material: str, plant: str) -> list[dict]:
	return _read(orders.boms_for_material, material, plant)


@frappe.whitelist()
def get_work_centers(plant: str) -> list[dict]:
	return _read(orders.work_centers, plant)


# Postings, through the outbox


@frappe.whitelist(methods=["POST"])
def confirm_order(
	order: str,
	operation: str,
	idempotency_key: str,
	yield_quantity=None,
	unit: str = "",
	scrap_quantity=None,
	rework_quantity=None,
	sequence: str = "0",
	plant: str = "",
	work_center: str = "",
	posting_date=None,
	final=None,
	personnel: str = "",
	variance_reason: str = "",
	activities=None,
	start=None,
	end=None,
	goods_movements_items=None,
	process_order=False,
	extra=None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue a confirmation of one operation of an order.

	`activities` is a JSON list of {"position", "quantity", "unit"}; `goods_movements_items` a JSON
	list of {"material", "plant", "quantity", "unit", "movement_type", "batch", "storage_location",
	"reservation", "reservation_item"} posted with the confirmation. `start` and `end` are the
	execution times. The idempotency key names the business event (for example the FoaMES record
	and step that is being confirmed), so repeating the call cannot post twice.
	"""
	try:
		payload = confirmations.confirmation(
			order,
			operation,
			yield_quantity,
			unit,
			scrap_quantity=scrap_quantity,
			rework_quantity=rework_quantity,
			sequence=sequence,
			plant=plant,
			work_center=work_center,
			posting_date=posting_date,
			final=None if final in (None, "") else bool(int(final)),
			personnel=personnel,
			variance_reason=variance_reason,
			activities=[confirmations.Activity(**a) for a in (_loads(activities, "activities") or [])],
			times=confirmations.ExecutionTimes(start=start, end=end) if (start or end) else None,
			goods_movements=[
				confirmations.GoodsMovementItem(**item)
				for item in (_loads(goods_movements_items, "goods_movements_items") or [])
			],
			extra=_loads(extra, "extra"),
		)
	except (ValueError, TypeError) as e:
		frappe.throw(str(e))
	op = confirmations.PROCESS if bool(int(process_order or 0)) else confirmations.PRODUCTION
	return _enqueue(op, payload, idempotency_key, str(order), reference_doctype, reference_name)


@frappe.whitelist(methods=["POST"])
def post_goods_receipt(
	order: str,
	material: str,
	plant: str,
	quantity,
	unit: str,
	idempotency_key: str,
	storage_location: str = "",
	batch: str = "",
	posting_date=None,
	is_completely_delivered=None,
	stock_type: str = "",
	manufacture_date=None,
	shelf_life_expiration_date=None,
	reversal=False,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue a goods receipt of an order's product (101), or its reversal (102)."""
	try:
		payload = goods_movements.goods_receipt_for_order(
			order,
			material,
			plant,
			quantity,
			unit,
			storage_location=storage_location,
			batch=batch,
			posting_date=posting_date,
			is_completely_delivered=None
			if is_completely_delivered in (None, "")
			else bool(int(is_completely_delivered)),
			stock_type=stock_type,
			manufacture_date=manufacture_date,
			shelf_life_expiration_date=shelf_life_expiration_date,
			reversal=bool(int(reversal or 0)),
		)
	except (ValueError, TypeError) as e:
		frappe.throw(str(e))
	return _enqueue(
		goods_movements.OPERATION, payload, idempotency_key, str(order), reference_doctype, reference_name
	)


@frappe.whitelist(methods=["POST"])
def post_goods_issue(
	order: str,
	components,
	idempotency_key: str,
	posting_date=None,
	reversal=False,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue the consumption of components for an order (261), or its reversal (262). `components`
	is a JSON list of {"material", "plant", "quantity", "unit", "batch", "storage_location",
	"reservation", "reservation_item"}."""
	try:
		payload = goods_movements.goods_issue_to_order(
			order,
			_loads(components, "components") or [],
			posting_date=posting_date,
			reversal=bool(int(reversal or 0)),
		)
	except (ValueError, TypeError) as e:
		frappe.throw(str(e))
	return _enqueue(
		goods_movements.OPERATION, payload, idempotency_key, str(order), reference_doctype, reference_name
	)


@frappe.whitelist(methods=["POST"])
def post_transfer(
	material: str,
	plant: str,
	quantity,
	unit: str,
	idempotency_key: str,
	from_storage_location: str = "",
	to_storage_location: str = "",
	to_plant: str = "",
	batch: str = "",
	to_batch: str = "",
	movement_type: str = goods_movements.TRANSFER_STORAGE_LOCATION,
	from_stock_type: str = "",
	to_stock_type: str = "",
	posting_date=None,
	reason_code: str = "",
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue a transfer posting between storage locations, plants or stock types."""
	try:
		payload = goods_movements.transfer_posting(
			material,
			plant,
			quantity,
			unit,
			from_storage_location=from_storage_location,
			to_storage_location=to_storage_location,
			to_plant=to_plant,
			batch=batch,
			to_batch=to_batch,
			movement_type=movement_type,
			from_stock_type=from_stock_type,
			to_stock_type=to_stock_type,
			posting_date=posting_date,
			reason_code=reason_code,
		)
	except (ValueError, TypeError) as e:
		frappe.throw(str(e))
	return _enqueue(
		goods_movements.OPERATION, payload, idempotency_key, sequence_group, reference_doctype, reference_name
	)


@frappe.whitelist(methods=["POST"])
def post_scrap(
	material: str,
	plant: str,
	quantity,
	unit: str,
	idempotency_key: str,
	storage_location: str = "",
	batch: str = "",
	cost_center: str = "",
	reason_code: str = "",
	posting_date=None,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue a scrapping of stock (551)."""
	try:
		payload = goods_movements.scrap(
			material,
			plant,
			quantity,
			unit,
			storage_location=storage_location,
			batch=batch,
			cost_center=cost_center,
			reason_code=reason_code,
			posting_date=posting_date,
		)
	except (ValueError, TypeError) as e:
		frappe.throw(str(e))
	return _enqueue(
		goods_movements.OPERATION, payload, idempotency_key, sequence_group, reference_doctype, reference_name
	)


@frappe.whitelist(methods=["POST"])
def cancel_confirmation(
	confirmation_group: str,
	confirmation_count: str,
	idempotency_key: str,
	posting_date=None,
	process_order=False,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue the cancellation of a confirmation. S/4HANA posts a reversal confirmation and reverses
	the goods movements that came with the original."""
	operation, payload = actions.cancel_confirmation(
		confirmation_group, confirmation_count, posting_date, process_order=bool(int(process_order or 0))
	)
	return _enqueue(operation, payload, idempotency_key, sequence_group, reference_doctype, reference_name)


@frappe.whitelist(methods=["POST"])
def reverse_material_document(
	year: str,
	document: str,
	idempotency_key: str,
	posting_date=None,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue the reversal of a whole material document."""
	operation, payload = actions.reverse_material_document(year, document, posting_date)
	return _enqueue(operation, payload, idempotency_key, sequence_group, reference_doctype, reference_name)
