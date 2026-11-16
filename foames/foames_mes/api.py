# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Machine-event ingest for PLC gateways, IoT bridges and the FoaMES gateways.

POST JSON to /api/method/foames.foames_mes.api.ingest_machine_events with the body
{"events": [...]} (or a single event object), signed as described in foames.foames_mes.signing.
Each event is {"machine": "<source id>", "type": "State|Count|Measurement|Alarm|Message",
"timestamp": ..., ...}. Unsigned calls need a logged-in user with the FoaMES Operator role.
"""

import json

import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password

from foames.foames_kernel.access import readable, require_read
from foames.foames_mes.doctype.machine.machine import get_machine_by_source
from foames.foames_mes.gateway.mapping import EventError, normalise_event
from foames.foames_mes.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep
def ingest_machine_events():
	body = frappe.request.get_data() if frappe.request else b""
	if not _authorised(body):
		frappe.throw(_("Invalid or missing signature"), frappe.AuthenticationError)
	try:
		data = json.loads(body or b"{}")
	except ValueError:
		frappe.throw(_("Body must be JSON"))
	if isinstance(data, list):
		events = data
	elif isinstance(data, dict) and "events" in data:
		events = data.get("events")
	else:
		events = [data]
	if not isinstance(events, list):
		frappe.throw(_("events must be a list"))
	source = "Webhook" if frappe.session.user == "Guest" else "Manual"
	return record_events(events, source=source)


def _authorised(body: bytes) -> bool:
	roles = set(frappe.get_roles())
	if frappe.session.user != "Guest" and roles & {"FoaMES Operator", "FoaMES Engineer", "System Manager"}:
		return True
	secret = get_decrypted_password(
		"Machine Data Settings", "Machine Data Settings", "webhook_secret", raise_exception=False
	)
	if not secret:
		return False
	headers = frappe.request.headers
	tolerance = frappe.db.get_single_value("Machine Data Settings", "signature_tolerance_seconds") or 300
	return verify(secret, headers.get(TIMESTAMP_HEADER), body, headers.get(SIGNATURE_HEADER), tolerance)


def record_events(events: list[dict], source: str = "Manual") -> dict:
	"""Store a batch of raw events. Returns what was accepted and why the rest was not."""
	accepted, rejected = [], []
	for raw in events or []:
		try:
			name = record_event(raw, source)
			accepted.append(name)
		except EventError as e:
			rejected.append({"event": raw, "reason": str(e)})
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			# The event key is a unique column, so Frappe raises UniqueValidationError for a repeat.
			rejected.append({"event": raw, "reason": "duplicate event id"})
	return {"accepted": accepted, "rejected": rejected}


def record_event(raw: dict, source: str = "Manual") -> str:
	event = normalise_event(raw, source, tz=site_timezone())
	machine = get_machine_by_source(event.pop("source_id"))
	if not machine:
		raise EventError(f"no enabled machine has source id {raw.get('machine') or raw.get('source_id')!r}")
	payload = event.pop("payload")
	doc = frappe.get_doc(
		{"doctype": "Machine Event", "machine": machine, "payload": json.dumps(payload, default=str), **event}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def site_timezone():
	"""The zone Frappe stores naive datetimes in, so gateway timestamps compare with now_datetime()."""
	from zoneinfo import ZoneInfo

	from frappe.utils import get_system_timezone

	try:
		return ZoneInfo(get_system_timezone())
	except Exception:
		return None


# Current job -------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def set_current_job(machine: str, reference: str | None = None, at=None) -> dict:
	"""Start a job on a machine, or end its current job by passing no reference.

	`reference` is an External Reference of type Job Card (any ERP). From `at` (default now) the
	machine's counts and run time belong to that job; the ERP adapter rolls up the job that ended.
	Needs write permission on the Machine (roles FoaMES Operator and Engineer have it).
	"""
	doc = frappe.get_doc("Machine", machine)
	doc.check_permission("write")
	doc.set_current_job(reference or None, at)
	return {
		"machine": doc.name,
		"current_job_reference": doc.current_job_reference,
		"current_job_since": doc.current_job_since,
	}


# Floor and suggestions --------------------------------------------------------------------------


@frappe.whitelist()
def get_floor_snapshot(days: int = 1) -> dict:
	"""The whole floor as one dict: machines with their counts and latest OEE, downtime by machine,
	missing ERP references and open suggestions. For the visual floor page and for external agents.
	Holds only the machines and records the caller may read."""
	from foames.foames_mes.floor import floor_snapshot

	frappe.has_permission("Machine", "read", throw=True)
	return floor_snapshot(int(days), for_user=True)


@frappe.whitelist()
def run_suggestion_rules(days: int = 1) -> list[str]:
	"""Run the built-in and registered rules now and return the suggestions created."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
	from foames.foames_mes.floor import collect_findings, floor_snapshot

	frappe.has_permission("Agent Suggestion", "create", throw=True)
	# The rules see the whole floor, as the scheduler's do; the caller is told only about the
	# suggestions they may read.
	return readable("Agent Suggestion", raise_suggestions(collect_findings(floor_snapshot(int(days)))))


@frappe.whitelist()
def post_suggestion(
	title: str,
	category: str,
	suggestion: str,
	agent: str,
	severity: str = "Warning",
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	evidence=None,
	rule_key: str | None = None,
) -> str:
	"""An external agent (for example through MCP) posts one suggestion for people to act on."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	frappe.has_permission("Agent Suggestion", "create", throw=True)
	if isinstance(evidence, str):
		evidence = json.loads(evidence)
	finding = {
		"title": title,
		"category": category,
		"suggestion": suggestion,
		"severity": severity,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"evidence": evidence or {},
		"rule_key": rule_key or f"{agent}:{frappe.generate_hash(length=12)}",
	}
	created = raise_suggestions([finding], agent=agent)
	return (
		created[0]
		if created
		else frappe.db.get_value("Agent Suggestion", {"rule_key": finding["rule_key"]}, "name")
	)


# Material flow ---------------------------------------------------------------------------------------


@frappe.whitelist()
def get_material_status(machine: str | None = None) -> dict:
	"""Lineside bins and material queues as last checked, for the whole floor or one machine: stock on
	hand, use per hour, hours to dry, what to call for, queue counts and MPC levels."""
	from foames.foames_mes.material_flow import BIN_FIELDS, QUEUE_FIELDS, machine_summary

	frappe.has_permission("Lineside Bin", "read", throw=True)
	frappe.has_permission("Material Queue", "read", throw=True)
	filters = {"disabled": 0}
	if machine:
		require_read("Machine", machine)
		filters["machine"] = machine
	bins = frappe.get_list(
		"Lineside Bin", filters=filters, fields=list(BIN_FIELDS), order_by="name", limit_page_length=0
	)
	queues = frappe.get_list(
		"Material Queue", filters=filters, fields=list(QUEUE_FIELDS), order_by="name", limit_page_length=0
	)
	result = {"bins": bins, "queues": queues}
	if machine:
		result["summary"] = machine_summary(machine, bins, queues)
	return result


@frappe.whitelist()
def get_dispatch_list(queue: str) -> list[dict]:
	"""Material that may start now in one queue, in the order its dispatch rule picks. Entries still
	conditioning, past their queue-time limit, expired or on hold are left out."""
	from foames.foames_mes.material_flow import dispatch_list

	frappe.has_permission("Material Queue Entry", "read", throw=True)
	require_read("Material Queue", queue)
	return dispatch_list(queue)


@frappe.whitelist()
def get_material_readiness(machine: str, hours: float = 0) -> dict:
	"""Whether a machine has the material to run for the next `hours`: bins that run dry inside the
	window and queue entries ready to start. For schedulers and agents deciding what to start."""
	from foames.foames_mes.material_flow import material_readiness

	frappe.has_permission("Lineside Bin", "read", throw=True)
	frappe.has_permission("Material Queue Entry", "read", throw=True)
	require_read("Machine", machine)
	return material_readiness(machine, float(hours or 0))


@frappe.whitelist(methods=["POST"])
def check_lineside_bin(bin: str) -> dict:
	"""Read one bin's stock from the ERP and recompute its forecast now. Changes only the FoaMES record."""
	from foames.foames_mes.material_flow import refresh_bin

	frappe.has_permission("Lineside Bin", "write", doc=bin, throw=True)
	row = refresh_bin(bin)
	return {"status": row["assessment"]["status"], **row["assessment"], "dry_at": row["dry_at"]}
