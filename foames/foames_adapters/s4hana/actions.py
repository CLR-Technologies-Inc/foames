# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Function imports that undo a posting: cancelling an order confirmation and reversing a material
document. S/4HANA exposes both as OData function imports (POST with the parameters in the URL),
not as entity creates, so they get their own outbox path.

Neither function can carry an idempotency marker. Instead, before a repeat attempt the outbox asks
S/4HANA whether the original is already undone: a confirmation reports `IsReversed`, and a reversal
material document names the document it reverses in `ReversedMaterialDocument`. The first attempt
is only ever repeated after an unclear answer, exactly like a create.

This module has no Frappe imports.
"""

from dataclasses import dataclass

from foames.foames_adapters.s4hana.odata import ODataClient, ODataError, error_from_response, literal
from foames.foames_adapters.s4hana.values import date_string


@dataclass
class Action:
	label: str
	service: str
	function: str
	# Parameters the payload must carry, and those it may.
	required: tuple[str, ...]
	optional: tuple[str, ...]
	# Parameters S/4HANA types as Edm.DateTime; they are sent as datetime'...' literals.
	date_parameters: tuple[str, ...]
	# Fields of the entity the function returns that identify the new document, joined with "|".
	document_fields: tuple[str, ...]
	# Kernel reference type of the new document, if the kernel has one.
	reference_type: str | None = None


ACTIONS: dict[str, Action] = {
	"Confirmation Cancellation": Action(
		label="Confirmation Cancellation",
		service="API_PROD_ORDER_CONFIRMATION_2_SRV",
		function="CancelProdnOrdConf",
		required=("ConfirmationGroup", "ConfirmationCount"),
		optional=("PostingDate", "ConfirmationText"),
		date_parameters=("PostingDate",),
		document_fields=("ConfirmationGroup", "ConfirmationCount"),
	),
	"Process Confirmation Cancellation": Action(
		label="Process Confirmation Cancellation",
		service="API_PROC_ORDER_CONFIRMATION_2_SRV",
		function="CancelProcOrdConf",
		required=("ConfirmationGroup", "ConfirmationCount"),
		optional=("PostingDate", "ConfirmationText"),
		date_parameters=("PostingDate",),
		document_fields=("ConfirmationGroup", "ConfirmationCount"),
	),
	"Material Document Reversal": Action(
		label="Material Document Reversal",
		service="API_MATERIAL_DOCUMENT_SRV",
		function="Cancel",
		required=("MaterialDocumentYear", "MaterialDocument"),
		optional=("PostingDate",),
		date_parameters=("PostingDate",),
		document_fields=("MaterialDocumentYear", "MaterialDocument"),
		reference_type="Stock Movement",
	),
}

CONFIRMATION_ENTITY_SETS = {
	"API_PROD_ORDER_CONFIRMATION_2_SRV": "ProdnOrdConf2",
	"API_PROC_ORDER_CONFIRMATION_2_SRV": "ProcOrdConf2",
}


def prepare(action: Action, payload: dict) -> dict:
	"""The parameters as sent: only the known ones, with the required ones present."""
	missing = [name for name in action.required if not payload.get(name)]
	if missing:
		raise ValueError(f"{action.label} needs {', '.join(missing)}")
	unknown = sorted(set(payload) - set(action.required) - set(action.optional))
	if unknown:
		raise ValueError(f"{action.label} does not take {', '.join(unknown)}")
	prepared = {}
	for name in action.required + action.optional:
		value = payload.get(name)
		if value in (None, ""):
			continue
		prepared[name] = date_string(value) if name in action.date_parameters else str(value)
	return prepared


def parameter_literal(action: Action, name: str, value: str) -> str:
	if name in action.date_parameters:
		return "datetime'" + value[:16] + "'"
	return literal(value)


def call(client: ODataClient, action: Action, parameters: dict) -> dict:
	"""POST the function import with a CSRF token, refreshing the token once if it expired."""
	query = {name: parameter_literal(action, name, value) for name, value in parameters.items()}
	url = client.url(action.service, action.function, query)
	for attempt in range(2):
		headers = client.headers({"X-CSRF-Token": client.csrf_token(action.service, refresh=attempt > 0)})
		headers["Content-Length"] = "0"
		response = client.send("POST", url, headers, b"")
		token_required = (
			response.status == 403 and (response.header("x-csrf-token") or "").lower() == "required"
		)
		if not token_required:
			break
	if response.status >= 400:
		raise error_from_response(response)
	data = response.json() or {}
	data = data.get("d", data)
	# A function import answers with the entity under the function's name, or directly.
	if isinstance(data, dict) and action.function in data and isinstance(data[action.function], dict):
		data = data[action.function]
	return data if isinstance(data, dict) else {}


def document_id(action: Action, entity: dict) -> str:
	return "|".join(str(entity.get(name) or "") for name in action.document_fields)


def find_existing(client: ODataClient, action: Action, parameters: dict) -> dict | None:
	"""The result of an earlier, successful attempt of this action, if S/4HANA has one."""
	if action.service in CONFIRMATION_ENTITY_SETS:
		entity = client.get_entity(
			action.service,
			CONFIRMATION_ENTITY_SETS[action.service],
			{name: parameters[name] for name in action.required},
		)
		if entity and entity.get("IsReversed"):
			return entity
		return None
	if action.function == "Cancel":
		results = client.query(
			action.service,
			"A_MaterialDocumentItem",
			{
				"ReversedMaterialDocumentYear": parameters["MaterialDocumentYear"],
				"ReversedMaterialDocument": parameters["MaterialDocument"],
			},
			top=1,
			select=["MaterialDocumentYear", "MaterialDocument"],
		)
		return results[0] if results else None
	return None


def send(client: ODataClient, action: Action, parameters: dict, verify_first: bool):
	"""Run once. With `verify_first`, check whether an earlier attempt already went through."""
	from foames.foames_adapters.s4hana.outbox import Outcome

	try:
		if verify_first:
			existing = find_existing(client, action, parameters)
			if existing:
				return Outcome("Posted", document_id(action, existing), response=existing)
		created = call(client, action, parameters)
		return Outcome("Posted", document_id(action, created), response=created)
	except ODataError as e:
		if not e.transient:
			return Outcome("Failed", error=str(e), details=e.details)
		return Outcome(
			"Unknown" if e.maybe_applied or verify_first else "Retry", error=str(e), details=e.details
		)


def cancel_confirmation(
	confirmation_group: str, confirmation_count: str, posting_date=None, process_order: bool = False
) -> tuple[str, dict]:
	"""The outbox operation and payload that cancel one confirmation."""
	operation = "Process Confirmation Cancellation" if process_order else "Confirmation Cancellation"
	payload = {"ConfirmationGroup": str(confirmation_group), "ConfirmationCount": str(confirmation_count)}
	if posting_date:
		payload["PostingDate"] = date_string(posting_date)
	return operation, payload


def reverse_material_document(year: str, document: str, posting_date=None) -> tuple[str, dict]:
	"""The outbox operation and payload that reverse one material document."""
	payload = {"MaterialDocumentYear": str(year), "MaterialDocument": str(document)}
	if posting_date:
		payload["PostingDate"] = date_string(posting_date)
	return "Material Document Reversal", payload
