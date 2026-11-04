# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Posts closed Downtime Records to ERPNext as Downtime Entries.

ERPNext keeps a Downtime Entry per stretch a Workstation was down (workstation, from, to,
operator, stop reason, remarks) and reports on it. With **Post Downtime to ERPNext** on, a
Downtime Record that closes on a Machine pointing at an ERPNext Workstation is queued as one
`Downtime Entry` posting. The posting carries the record's name, so an entry is created once and
then updated when the record changes afterwards, which is the normal order of things on a floor:
the machine stops and starts by itself, and a person assigns the reason later.

ERPNext's stop reasons are a fixed list. A Downtime Reason whose title is one of them maps to it
directly; otherwise its category decides (Changeover, Breakdown, Planned), and anything else is
`Other`, with the FoaMES reason and notes in the entry's remarks. ERPNext also requires an
operator on every entry, taken from **Downtime Operator** in the settings.
"""

from __future__ import annotations

import hashlib
import json

import frappe

from foames.foames_adapters.erpnext import erpnext_installed
from foames.foames_adapters.erpnext.floor import machine_workstations
from foames.foames_adapters.erpnext.postings import stop_reason_for

OPERATION = "Downtime Entry"


def posting_enabled() -> bool:
	if not erpnext_installed():
		return False
	settings = frappe.get_cached_doc("ERPNext Adapter Settings")
	return bool(settings.enable_postings and settings.post_downtime_to_erpnext)


def on_update(doc, method=None) -> str | None:
	"""Registered under `doc_events` for Downtime Record. Returns the outbox record queued, if any."""
	if doc.status != "Closed" or not doc.end_time or not posting_enabled():
		return None
	workstation = machine_workstations([doc.machine]).get(doc.machine)
	if not workstation:
		return None
	return queue_downtime(doc, workstation)


def payload_for(doc, workstation: str) -> dict:
	title, category = None, None
	if doc.reason:
		title, category = frappe.db.get_value("Downtime Reason", doc.reason, ["title", "category"]) or (
			None,
			None,
		)
	settings = frappe.get_cached_doc("ERPNext Adapter Settings")
	parts = [doc.machine]
	if doc.reason:
		parts.append(f"{doc.reason} ({title})" if title and title != doc.reason else doc.reason)
	if doc.notes:
		parts.append(doc.notes.strip())
	payload = {
		"workstation": workstation,
		"from_time": str(doc.start_time),
		"to_time": str(doc.end_time),
		"stop_reason": stop_reason_for(title or doc.reason, category),
		"remarks": ": ".join(parts[:2]) + (f". {parts[2]}" if len(parts) > 2 else ""),
		"downtime_record": doc.name,
	}
	if settings.downtime_operator:
		payload["operator"] = settings.downtime_operator
	return payload


def queue_downtime(doc, workstation: str) -> str:
	"""One posting per distinct content of the record: the same close queued twice is one posting,
	and a later change (a reason filled in) is a new posting that updates the same entry."""
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue

	payload = payload_for(doc, workstation)
	digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
	return enqueue(
		OPERATION,
		payload,
		f"downtime:{doc.name}:{digest}",
		sequence_group=f"downtime:{workstation}",
		reference_doctype="Downtime Record",
		reference_name=doc.name,
	)
