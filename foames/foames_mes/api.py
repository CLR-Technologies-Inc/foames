# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Machine-event ingest for PLC gateways, IoT bridges and the FoaMES gateways.

POST JSON to /api/method/foames.foames_mes.api.ingest_machine_events with the body
{"events": [...]} (or a single event object), signed as described in foames.foames_mes.signing.
Each event is {"machine": "<source id>", "type": "State|Count|Measurement|Alarm|Message",
"timestamp": ..., ...}. Unsigned calls need a logged-in user with the FoaMES Operator role.
"""

import json

import frappe
from frappe import _

from foames.foames_mes.doctype.machine.machine import get_machine_by_source
from foames.foames_mes.gateway.mapping import EventError, normalise_event
from foames.foames_mes.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify


@frappe.whitelist(allow_guest=True, methods=["POST"])
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
	secret = frappe.utils.password.get_decrypted_password(
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
		except frappe.DuplicateEntryError:
			rejected.append({"event": raw, "reason": "duplicate event id"})
	return {"accepted": accepted, "rejected": rejected}


def record_event(raw: dict, source: str = "Manual") -> str:
	event = normalise_event(raw, source)
	machine = get_machine_by_source(event.pop("source_id"))
	if not machine:
		raise EventError(f"no enabled machine has source id {raw.get('machine') or raw.get('source_id')!r}")
	payload = event.pop("payload")
	doc = frappe.get_doc(
		{"doctype": "Machine Event", "machine": machine, "payload": json.dumps(payload, default=str), **event}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


# Floor and suggestions --------------------------------------------------------------------------


@frappe.whitelist()
def get_floor_snapshot(days: int = 1) -> dict:
	"""The whole floor as one dict: machines with their counts and latest OEE, downtime by machine,
	missing ERP references and open suggestions. For the visual floor page and for external agents."""
	from foames.foames_mes.floor import floor_snapshot

	frappe.has_permission("Machine", "read", throw=True)
	return floor_snapshot(int(days))


@frappe.whitelist()
def run_suggestion_rules(days: int = 1) -> list[str]:
	"""Run the built-in and registered rules now and return the suggestions created."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
	from foames.foames_mes.floor import collect_findings, floor_snapshot

	frappe.has_permission("Agent Suggestion", "create", throw=True)
	return raise_suggestions(collect_findings(floor_snapshot(int(days))))


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
