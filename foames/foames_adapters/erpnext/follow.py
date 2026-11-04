# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Machines follow the Job Cards people start and finish in ERPNext.

Operators who start a Job Card in ERPNext (its **Start Job** button, or a time log posting) and
complete it there should not have to tell FoaMES as well. With **Follow Job Cards Started in
ERPNext** on, the Job Card's `on_change` event does it: the moment a card goes Work In Progress it
becomes the current job of every machine at its workstation that has no current job, and a card
that is completed, cancelled, discarded or deleted ends on the machines working on it. Ending a
job is what makes the adapter roll the machine's counts up to the card (while it is still a draft)
and inspect it from what the machine measured, so the next card starts with a clean window.

`on_change` rather than `on_update`: on ERPNext v16, Start Job and `make_time_log` write the time
log row and set the card's status with `db_set`, which runs `on_change` but never saves the card.
Frappe loads the document as it was before a `db_set` or a save, so the handler sees the
transition and acts on it only: an unrelated edit of a card that is already in progress does not
hand idle machines to it again. A machine busy on another Job Card is left alone: which of two
cards a shared workstation's machine is on is the floor's call, through the Machine form,
`set_current_job` or an agent.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_datetime, now_datetime

from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed

ENDED_STATUSES = ("Completed", "Cancelled")
IN_PROGRESS = "Work In Progress"


def follow_enabled() -> bool:
	if not erpnext_installed():
		return False
	return bool(frappe.get_cached_doc("ERPNext Adapter Settings").follow_job_cards_started_in_erpnext)


def on_job_card_change(doc, method=None):
	"""Registered on the Job Card's `on_change`: after every save, submit and cancel, and after
	ERPNext sets the card's status with `db_set` (a discard, or Start Job on v16)."""
	if doc.doctype != "Job Card" or not follow_enabled():
		return
	if doc.docstatus == 2 or doc.status in ENDED_STATUSES:
		end_on_machines(doc)
		return
	if doc.docstatus != 0 or doc.status != IN_PROGRESS:
		return
	before = doc.get_doc_before_save()
	if before is not None and before.get("status") == IN_PROGRESS and not before.get("docstatus"):
		return  # Already in progress: an unrelated edit does not reassign machines.
	start_on_idle_machines(doc)


def on_job_card_trash(doc, method=None):
	"""A deleted Job Card ends on the machines working on it, without queuing anything for it: a
	posting for a card that is about to be gone could only fail. Its reference stays, Missing."""
	if doc.doctype != "Job Card" or not follow_enabled():
		return
	end_on_machines(doc, skip_postings=True)


def start_on_idle_machines(doc) -> list[str]:
	"""Make the Job Card the current job of the machines at its workstation that have none, from
	the moment its open time log started (or now), but not before the machine's last roll-up, so
	counts already attributed to an earlier card are not counted again. Returns the machines
	started."""
	if not doc.get("workstation"):
		return []
	from foames.foames_adapters.erpnext.rollup import last_rollup_end
	from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

	started = []
	reference = None
	for machine in machines_at(doc.workstation):
		if machine.current_job_reference:
			continue
		reference = reference or get_reference("Job Card", doc.name, ADAPTER_KEY, ignore_permissions=True)
		at = started_at(doc)
		rolled_up_until = last_rollup_end(machine.name)
		if rolled_up_until and rolled_up_until > at:
			at = rolled_up_until
		set_job(machine.name, reference, at)
		started.append(machine.name)
	return started


def end_on_machines(doc, skip_postings: bool = False) -> list[str]:
	"""End the Job Card on every machine that has it as its current job, at the moment its last
	time log ended (or now). Returns the machines ended."""
	reference = frappe.db.get_value(
		"External Reference",
		{"erp_system": ADAPTER_KEY, "reference_type": "Job Card", "external_id": doc.name},
		"name",
	)
	if not reference:
		return []
	ended = []
	for name in frappe.get_all(
		"Machine", {"current_job_reference": reference}, pluck="name", order_by="name"
	):
		set_job(name, None, ended_at(doc), skip_postings=skip_postings)
		ended.append(name)
	return ended


def machines_at(workstation: str) -> list:
	"""The enabled machines whose Workstation Reference points at this ERPNext Workstation."""
	references = frappe.get_all(
		"External Reference",
		{"erp_system": ADAPTER_KEY, "reference_type": "Workstation", "external_id": workstation},
		pluck="name",
	)
	if not references:
		return []
	return frappe.get_all(
		"Machine",
		{"workstation_reference": ("in", references), "disabled": 0},
		["name", "current_job_reference"],
		order_by="name",
	)


def set_job(machine: str, reference: str | None, at, skip_postings: bool = False):
	"""The Machine's own job change, on behalf of whoever changed the Job Card in ERPNext. With
	`skip_postings`, the adapter's job-change hooks queue nothing for the job that ends."""
	doc = frappe.get_doc("Machine", machine)
	doc.flags.ignore_permissions = True
	doc.flags.skip_job_postings = skip_postings
	doc.set_current_job(reference, at)


def started_at(doc):
	"""When the card's open time log started (the earliest, with several operators), else now."""
	times = [
		get_datetime(row.from_time)
		for row in doc.get("time_logs") or []
		if row.get("from_time") and not row.get("to_time")
	]
	return min(times) if times else now_datetime()


def ended_at(doc):
	times = [get_datetime(row.to_time) for row in doc.get("time_logs") or [] if row.get("to_time")]
	return max(times) if times else now_datetime()
