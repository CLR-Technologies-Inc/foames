# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Whitelisted endpoints of the ERPNext adapter, for agents, operator screens and integrations.

All calls need a logged-in user. Reads need the FoaMES Operator, Engineer or Integration role (or
System Manager); queuing a posting needs create permission on ERPNext Outbox, and the posting is
then performed as that user, so ERPNext's own permissions on Stock Entry, Job Card and Work Order
apply.
"""

import json

import frappe
from frappe import _

from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed
from foames.foames_adapters.erpnext import postings as rules

READ_ROLES = ("System Manager", "FoaMES Engineer", "FoaMES Operator", "FoaMES Integration", "FoaMES Quality")


def _require_erpnext():
	if not erpnext_installed():
		frappe.throw(_("ERPNext is not installed on this site"), frappe.ValidationError)


def _require_read():
	_require_erpnext()
	if not set(frappe.get_roles()) & set(READ_ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_operations() -> list[dict]:
	"""The outbox operations and what each payload needs."""
	return [
		{
			"operation": op.label,
			"required": list(op.required),
			"optional": list(op.optional),
			"doctype": op.doctype,
			"reference_type": op.reference_type,
		}
		for op in rules.OPERATIONS.values()
	]


@frappe.whitelist()
def get_work_order(name: str) -> dict:
	"""A Work Order with its operations and required items, resolved through the adapter."""
	_require_read()
	from foames.foames_adapters import get_adapter

	resolved = get_adapter(ADAPTER_KEY).resolve("Work Order", name)
	if not resolved:
		frappe.throw(_("Work Order {0} does not exist").format(name), frappe.DoesNotExistError)
	return resolved.data


@frappe.whitelist()
def list_open_work_orders(workstation: str | None = None, limit: int = 100) -> list[dict]:
	_require_read()
	from foames.foames_adapters.erpnext.details import open_work_orders

	return open_work_orders(workstation, limit=int(limit))


@frappe.whitelist()
def list_open_job_cards(
	workstation: str | None = None, machine: str | None = None, limit: int = 200
) -> list[dict]:
	"""Open Job Cards, optionally for one workstation or for the workstation a Machine points at."""
	_require_read()
	from foames.foames_adapters.erpnext.details import open_job_cards
	from foames.foames_adapters.erpnext.floor import machine_workstations

	if machine:
		workstation = machine_workstations([machine]).get(machine)
		if not workstation:
			return []
	return open_job_cards(workstation, limit=int(limit))


@frappe.whitelist(methods=["POST"])
def post(
	operation: str,
	payload: str | dict,
	idempotency_key: str,
	sequence_group: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Queue a posting to ERPNext. Returns the outbox record and whether it was already queued."""
	_require_erpnext()
	frappe.has_permission("ERPNext Outbox", "create", throw=True)
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			frappe.throw(_("payload must be a JSON object"))
	if operation not in rules.OPERATIONS:
		frappe.throw(_("{0} is not an ERPNext outbox operation").format(frappe.bold(operation)))
	try:
		rules.prepare(rules.OPERATIONS[operation], payload)
	except ValueError as e:
		frappe.throw(str(e))
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue_posting

	name, created = enqueue_posting(
		operation, payload, idempotency_key, sequence_group, reference_doctype, reference_name
	)
	return {"outbox": name, "already_queued": not created, **get_posting(name)}


@frappe.whitelist()
def get_posting(name: str) -> dict:
	"""Status of a queued posting."""
	_require_read()
	values = frappe.db.get_value(
		"ERPNext Outbox",
		name,
		[
			"name",
			"operation",
			"status",
			"attempts",
			"next_attempt_at",
			"erp_doctype",
			"erp_document",
			"last_error",
		],
		as_dict=True,
	)
	if not values:
		frappe.throw(_("Posting {0} does not exist").format(name), frappe.DoesNotExistError)
	return values


@frappe.whitelist(methods=["POST"])
def process_outbox_now() -> int:
	"""Perform due postings now instead of waiting for the scheduler. For tests and operators."""
	frappe.only_for(("System Manager", "FoaMES Engineer"))
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import process_outbox

	return process_outbox()
