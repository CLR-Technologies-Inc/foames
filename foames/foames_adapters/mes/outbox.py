# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Outbox rules for writes to an MES: what an operation sends, how a write is kept from being
performed twice, and when a failed write is retried.

An operation declares its idempotency:

- **Upsert**: the system keys the record on something in the payload, so sending it again
  overwrites rather than duplicates. A retry after an unclear answer simply sends again.
- **Client Reference**: the payload carries a field the system keeps and can be searched by. The
  posting writes a marker derived from its idempotency key into that field; after an unclear
  answer the next attempt first searches for the marker and records the existing record.
- **Manual**: neither is available. After an unclear answer (a timeout, a dropped connection, a
  5xx) the posting stops in **Unknown** with no next attempt: a person checks the system and either
  cancels the posting or requeues it. It is never resent blind.

This module has no Frappe imports; the MES Outbox DocType applies these rules.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from foames.foames_adapters.mes.entities import value_at
from foames.foames_adapters.mes.profile import CLIENT_REFERENCE, GENERIC_REQUEST, MANUAL, UPSERT, Operation
from foames.foames_adapters.mes.rest import MESError, RestClient

MARKER_PREFIX = "FOAMES-"
BASE_DELAY_SECONDS = 60
MAX_DELAY_SECONDS = 6 * 3600
MAX_ATTEMPTS = 12
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def marker(idempotency_key: str) -> str:
	"""A 23-character marker written into the client reference field."""
	return MARKER_PREFIX + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16].upper()


def effective(operation: Operation, payload: dict) -> Operation:
	"""The generic request takes its method, path and idempotency from the payload itself."""
	if operation.label != GENERIC_REQUEST:
		return operation
	method = str(payload.get("method") or "POST").upper()
	kind = MANUAL
	if payload.get("reference_field") and payload.get("lookup_path"):
		kind = CLIENT_REFERENCE
	elif payload.get("idempotent") is True or (method == "PUT" and payload.get("idempotent") is not False):
		kind = UPSERT
	return Operation(
		label=GENERIC_REQUEST,
		method=method,
		path=str(payload.get("path") or ""),
		required=("method", "path"),
		idempotency=kind,
		reference_field=str(payload.get("reference_field") or ""),
		lookup_path=str(payload.get("lookup_path") or ""),
		lookup_query=str(payload.get("lookup_query") or ""),
		document_path=str(payload.get("document_path") or "id"),
	)


def body_of(operation: Operation, payload: dict):
	"""The request body: the whole payload, or for the generic request its `body`."""
	return payload.get("body") if operation.label == GENERIC_REQUEST else dict(payload)


def prepare(operation: Operation, payload: dict, idempotency_key: str) -> dict:
	"""The payload as sent: checked, copied, and carrying the marker for a Client Reference."""
	missing = [name for name in operation.required if not payload.get(name)]
	if missing:
		raise ValueError(f"{operation.label} needs {', '.join(missing)}")
	prepared = dict(payload)
	op = effective(operation, prepared)
	if op.method not in WRITE_METHODS:
		raise ValueError(f"{operation.label}: {op.method} is not a write method")
	if not op.path:
		raise ValueError(f"{operation.label} needs a path")
	if op.idempotency == CLIENT_REFERENCE:
		if operation.label == GENERIC_REQUEST:
			body = prepared.get("body")
			if not isinstance(body, dict):
				raise ValueError("A REST Request with a reference field needs a JSON object body")
			body = dict(body)
			body[op.reference_field] = marker(idempotency_key)
			prepared["body"] = body
		else:
			prepared[op.reference_field] = marker(idempotency_key)
	return prepared


def document_id(operation: Operation, payload: dict, answer) -> str:
	op = effective(operation, payload)
	if isinstance(answer, dict):
		value = value_at(answer, op.document_path)
		if value not in (None, ""):
			return str(value)
	if op.idempotency == UPSERT:
		return op.path
	return ""


def find_existing(client: RestClient, operation: Operation, payload: dict) -> dict | None:
	"""The record an earlier attempt of this posting created, if the system has one."""
	op = effective(operation, payload)
	body = body_of(operation, payload)
	mark = body.get(op.reference_field) if isinstance(body, dict) else None
	if not mark:
		return None
	query = {name: body.get(name) for name in op.lookup_fields if body.get(name) not in (None, "")}
	if op.lookup_query:
		query[op.lookup_query] = mark
	for record in client.get_list(op.lookup_path, query):
		if isinstance(record, dict) and value_at(record, op.reference_field) == mark:
			return record
	return None


@dataclass
class Outcome:
	status: str  # Posted, Retry, Unknown or Failed
	document: str = ""
	error: str = ""
	details: list | None = None
	response: dict | None = None
	# For a Manual operation after an unclear answer: no automatic retry.
	halt: bool = False


def send(client: RestClient, operation: Operation, payload: dict, verify_first: bool) -> Outcome:
	"""Send once. With `verify_first`, look for an earlier posting first where the operation allows."""
	op = effective(operation, payload)
	body = body_of(operation, payload)
	try:
		if verify_first and op.idempotency == CLIENT_REFERENCE:
			existing = find_existing(client, operation, payload)
			if existing:
				return Outcome("Posted", document_id(operation, payload, existing), response=existing)
		answer = client.write(op.method, op.path, body, idempotent=op.idempotency == UPSERT)
		return Outcome(
			"Posted",
			document_id(operation, payload, answer),
			response=answer if isinstance(answer, dict) else None,
		)
	except MESError as e:
		if not e.transient:
			return Outcome("Failed", error=str(e), details=e.details)
		if op.idempotency == UPSERT:
			return Outcome("Retry", error=str(e), details=e.details)
		unclear = e.maybe_applied or verify_first
		if not unclear:
			return Outcome("Retry", error=str(e), details=e.details)
		if op.idempotency == MANUAL:
			return Outcome(
				"Unknown",
				error=(
					f"{e} The request may have reached the system and {operation.label} cannot be checked "
					"automatically: check the system, then requeue or cancel this posting."
				),
				details=e.details,
				halt=True,
			)
		return Outcome("Unknown", error=str(e), details=e.details)


def retry_delay(attempts: int) -> int:
	"""Seconds to wait after the given number of failed attempts: 1, 2, 4 ... minutes, capped at 6 h."""
	return min(BASE_DELAY_SECONDS * 2 ** max(attempts - 1, 0), MAX_DELAY_SECONDS)


def give_up(attempts: int) -> bool:
	return attempts >= MAX_ATTEMPTS
