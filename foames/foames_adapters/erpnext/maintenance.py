# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Posts Maintenance Work Orders to ERPNext as Asset Repairs.

ERPNext keeps an Asset Repair per repair of a fixed Asset (failure and completion dates, a status,
what was done, the downtime it computes, and later the costs and parts consumed). With **Post
Maintenance Work Orders to ERPNext** on, a Maintenance Work Order that starts on a Machine pointing
at an ERPNext Asset (its **Asset Reference**) is queued as one `Asset Repair` posting with the
status Pending, which is how ERPNext marks the Asset Out of Order. Completing the work order queues
a second posting that brings the same repair to Completed, with the completion time and the
findings as the actions performed; cancelling it marks the repair Cancelled. Every posting carries
the work order's name, so the repair is created once and then updated.

A work order that is raised but never started tells ERPNext nothing: the machine is still running.
The repair stays a draft unless **Submit Asset Repairs When Complete** is on, so a person can add
the costs and the consumed items ERPNext books on submission.
"""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import now_datetime

from foames.foames_adapters.erpnext import erpnext_installed
from foames.foames_adapters.erpnext.floor import machine_records

OPERATION = "Asset Repair"
REPAIR_STATUS_BY_WORK_ORDER_STATUS = {
	"In Progress": "Pending",
	"Completed": "Completed",
	"Cancelled": "Cancelled",
}


def posting_enabled() -> bool:
	if not erpnext_installed():
		return False
	settings = frappe.get_cached_doc("ERPNext Adapter Settings")
	return bool(settings.enable_postings and settings.post_maintenance_to_erpnext)


def machine_assets(machines: list[str]) -> dict[str, str]:
	"""Machine name -> ERPNext Asset name, for machines whose Asset Reference points at ERPNext."""
	return machine_records(machines, "asset_reference", "Asset")


def on_update(doc, method=None) -> str | None:
	"""Registered under `doc_events` for Maintenance Work Order. Returns the outbox record queued,
	if any: nothing for an open work order, and nothing for a cancellation that never started.

	A work order whose repair exists already is finished on that repair's asset, even when the
	machine's Asset Reference changed or was cleared since, and even when the setting was turned
	off since: a Pending repair left behind would keep the asset Out of Order in ERPNext."""
	if doc.status not in REPAIR_STATUS_BY_WORK_ORDER_STATUS or not erpnext_installed():
		return None
	asset = posted_asset(doc.name)
	if asset is None:
		if doc.status == "Cancelled" or not posting_enabled():
			return None
		asset = machine_assets([doc.machine]).get(doc.machine)
		if not asset:
			return None
	return queue_repair(doc, asset)


def posted_asset(work_order: str) -> str | None:
	"""The asset the work order's repair was queued for, from its latest live posting."""
	rows = frappe.get_all(
		"ERPNext Outbox",
		filters={
			"operation": OPERATION,
			"reference_doctype": "Maintenance Work Order",
			"reference_name": work_order,
			"status": ("!=", "Cancelled"),
		},
		fields=["payload"],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return None
	return (json.loads(rows[0].payload or "{}")).get("asset") or None


def payload_for(doc, asset: str) -> dict:
	status = REPAIR_STATUS_BY_WORK_ORDER_STATUS[doc.status]
	parts = [f"{doc.name}: {doc.title}" if doc.title else doc.name, doc.machine]
	if doc.maintenance_plan:
		parts.append(f"Maintenance Plan {doc.maintenance_plan}")
	payload = {
		"asset": asset,
		"failure_date": str(doc.started_on or doc.due_on or now_datetime()),
		"repair_status": status,
		"description": ". ".join(parts),
		"maintenance_work_order": doc.name,
	}
	if status == "Completed":
		payload["completion_date"] = str(doc.completed_on)
		if doc.findings:
			payload["actions_performed"] = doc.findings.strip()
		settings = frappe.get_cached_doc("ERPNext Adapter Settings")
		payload["submit"] = bool(settings.submit_asset_repairs)
	return payload


def queue_repair(doc, asset: str) -> str:
	"""One posting per distinct content of the work order: the same state saved twice is one
	posting, and a later change (completion, findings) is a new posting that updates the same
	repair. Postings for one work order run in order."""
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue

	payload = payload_for(doc, asset)
	digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
	return enqueue(
		OPERATION,
		payload,
		f"maintenance:{doc.name}:{digest}",
		sequence_group=f"asset-repair:{doc.name}",
		reference_doctype="Maintenance Work Order",
		reference_name=doc.name,
	)
