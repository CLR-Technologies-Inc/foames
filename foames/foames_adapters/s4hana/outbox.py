# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Outbox rules for postings to S/4HANA: what each operation posts, how a posting is made
idempotent, and when a failed posting is retried.

S/4HANA's OData create calls have no idempotency key of their own. So every posting writes a short
marker derived from its idempotency key into a text field of the document it creates (the
confirmation text or the material document header text). When a send ends without a clear answer
(a timeout, a dropped connection, a 5xx), the next attempt first searches S/4HANA for that marker
and records the existing document instead of posting a second one.

This module has no Frappe imports; the S4HANA Outbox DocType applies these rules.
"""

import hashlib
from dataclasses import dataclass

from foames.foames_adapters.s4hana import actions
from foames.foames_adapters.s4hana.odata import ODataClient, ODataError

MARKER_PREFIX = "FOAMES-"
BASE_DELAY_SECONDS = 60
MAX_DELAY_SECONDS = 6 * 3600
MAX_ATTEMPTS = 12


@dataclass
class Operation:
	label: str
	service: str
	entity_set: str
	marker_field: str
	marker_length: int
	# Payload fields that, together with the marker, find an earlier posting.
	lookup_fields: tuple[str, ...]
	# Fields of the created entity that identify it, joined with "|".
	document_fields: tuple[str, ...]
	# Kernel reference type of the created document, if the kernel has one.
	reference_type: str | None = None


# Field names follow SAP's released APIs; check them against the system's $metadata.
OPERATIONS: dict[str, Operation] = {
	"Production Order Confirmation": Operation(
		label="Production Order Confirmation",
		service="API_PROD_ORDER_CONFIRMATION_2_SRV",
		entity_set="ProdnOrdConf2",
		marker_field="ConfirmationText",
		marker_length=40,
		lookup_fields=("OrderID",),
		document_fields=("ConfirmationGroup", "ConfirmationCount"),
	),
	"Process Order Confirmation": Operation(
		label="Process Order Confirmation",
		service="API_PROC_ORDER_CONFIRMATION_2_SRV",
		entity_set="ProcOrdConf2",
		marker_field="ConfirmationText",
		marker_length=40,
		lookup_fields=("OrderID",),
		document_fields=("ConfirmationGroup", "ConfirmationCount"),
	),
	"Goods Movement": Operation(
		label="Goods Movement",
		service="API_MATERIAL_DOCUMENT_SRV",
		entity_set="A_MaterialDocumentHeader",
		marker_field="MaterialDocumentHeaderText",
		marker_length=25,
		lookup_fields=(),
		document_fields=("MaterialDocumentYear", "MaterialDocument"),
		reference_type="Stock Movement",
	),
}


def operation(name: str) -> "Operation | actions.Action":
	"""The outbox operation of that name: an entity create from OPERATIONS, or a function import
	from actions.ACTIONS."""
	if name in OPERATIONS:
		return OPERATIONS[name]
	if name in actions.ACTIONS:
		return actions.ACTIONS[name]
	raise KeyError(name)


def operation_names() -> list[str]:
	return list(OPERATIONS) + list(actions.ACTIONS)


def marker(idempotency_key: str) -> str:
	"""A 23-character marker, short enough for the 25-character material document header text."""
	return MARKER_PREFIX + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16].upper()


def prepare(operation: Operation, payload: dict, idempotency_key: str) -> dict:
	"""The payload as sent: a copy with the marker written into the operation's text field."""
	if isinstance(operation, actions.Action):
		return actions.prepare(operation, payload)
	missing = [name for name in operation.lookup_fields if not payload.get(name)]
	if missing:
		raise ValueError(f"{operation.label} needs {', '.join(missing)}")
	prepared = dict(payload)
	prepared[operation.marker_field] = marker(idempotency_key)[: operation.marker_length]
	return prepared


def document_id(operation: Operation, entity: dict) -> str:
	return "|".join(str(entity.get(name) or "") for name in operation.document_fields)


def find_existing(client: ODataClient, operation: Operation, payload: dict) -> dict | None:
	"""The document an earlier attempt of this posting created, if S/4HANA has one."""
	filters = {name: payload[name] for name in operation.lookup_fields}
	filters[operation.marker_field] = payload[operation.marker_field]
	results = client.query(operation.service, operation.entity_set, filters, top=2)
	return results[0] if results else None


@dataclass
class Outcome:
	status: str  # Posted, Retry, Unknown or Failed
	document: str = ""
	error: str = ""
	details: list | None = None
	response: dict | None = None


def send(client: ODataClient, operation: Operation, payload: dict, verify_first: bool) -> Outcome:
	"""Post once. With `verify_first`, look for an earlier posting with the same marker first."""
	if isinstance(operation, actions.Action):
		return actions.send(client, operation, payload, verify_first)
	try:
		if verify_first:
			existing = find_existing(client, operation, payload)
			if existing:
				return Outcome("Posted", document_id(operation, existing), response=existing)
		created = client.post(operation.service, operation.entity_set, payload)
		return Outcome("Posted", document_id(operation, created), response=created)
	except ODataError as e:
		if not e.transient:
			return Outcome("Failed", error=str(e), details=e.details)
		# A send that may have reached S/4HANA is checked by marker on the next attempt.
		return Outcome(
			"Unknown" if e.maybe_applied or verify_first else "Retry", error=str(e), details=e.details
		)


def retry_delay(attempts: int) -> int:
	"""Seconds to wait after the given number of failed attempts: 1, 2, 4 ... minutes, capped at 6 h."""
	return min(BASE_DELAY_SECONDS * 2 ** max(attempts - 1, 0), MAX_DELAY_SECONDS)


def give_up(attempts: int) -> bool:
	return attempts >= MAX_ATTEMPTS
