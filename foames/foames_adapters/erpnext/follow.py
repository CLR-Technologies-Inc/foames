# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Machines follow the Job Cards people start and finish in ERPNext.

Operators who start a Job Card in ERPNext (its **Start Job** button, or a time log posting) and
complete it there should not have to tell FoaMES as well. With **Follow Job Cards Started in
ERPNext** on, the Job Card document events do it: a card that goes Work In Progress becomes the
current job of every machine at its workstation that has no current job, and a card that is
completed, cancelled or deleted ends on the machines working on it. Ending a job is what makes
the adapter roll the machine's counts up to the card (while it is still a draft) and inspect it
from what the machine measured, so the next card starts with a clean window. A machine busy on
another Job Card is left alone: which of two cards a shared workstation's machine is on is the
floor's call, through the Machine form, `set_current_job` or an agent.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_datetime, now_datetime

from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed

ENDED_STATUSES = ("Completed", "Cancelled")


def follow_enabled() -> bool:
	if not erpnext_installed():
		return False
	return bool(frappe.get_cached_doc("ERPNext Adapter Settings").follow_job_cards_started_in_erpnext)


def on_job_card_update(doc, method=None):
	"""Registered on the Job Card's `on_update`, `on_update_after_submit` and `on_cancel`."""
	if doc.doctype != "Job Card" or not follow_enabled():
		return
	if doc.docstatus == 2 or doc.status in ENDED_STATUSES:
		end_on_machines(doc)
	elif doc.docstatus == 0 and doc.status == "Work In Progress":
		start_on_idle_machines(doc)


def on_job_card_trash(doc, method=None):
	"""A deleted Job Card ends on the machines working on it; its reference stays and is Missing."""
	if doc.doctype != "Job Card" or not follow_enabled():
		return
	end_on_machines(doc)


def start_on_idle_machines(doc) -> list[str]:
	"""Make the Job Card the current job of the machines at its workstation that have none, from
	the moment its first time log started (or now). Returns the machines started."""
	if not doc.get("workstation"):
		return []
	from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

	started = []
	reference = None
	for machine in machines_at(doc.workstation):
		if machine.current_job_reference:
			continue
		reference = reference or get_reference("Job Card", doc.name, ADAPTER_KEY, ignore_permissions=True)
		set_job(machine.name, reference, started_at(doc))
		started.append(machine.name)
	return started


def end_on_machines(doc) -> list[str]:
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
		set_job(name, None, ended_at(doc))
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


def set_job(machine: str, reference: str | None, at):
	"""The Machine's own job change, on behalf of whoever saved the Job Card in ERPNext."""
	doc = frappe.get_doc("Machine", machine)
	doc.flags.ignore_permissions = True
	doc.set_current_job(reference, at)


def started_at(doc):
	times = [get_datetime(row.from_time) for row in doc.get("time_logs") or [] if row.get("from_time")]
	return min(times) if times else now_datetime()


def ended_at(doc):
	times = [get_datetime(row.to_time) for row in doc.get("time_logs") or [] if row.get("to_time")]
	return max(times) if times else now_datetime()
