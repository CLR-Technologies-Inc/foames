# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Rolls each machine's counts and run time up to the ERPNext Job Card it is working on.

A Machine names its job through `current_job_reference`, an External Reference of type Job Card.
Every few minutes (`roll_up_all`, from the scheduler) and whenever the job changes
(`on_job_changed`, from the core's `foames_machine_job_changed` hook) the adapter takes the window
since the last roll-up, sums the good and scrap counter deltas in it, finds the stretches the
machine was Running, and queues one `Job Card Production Log` posting for the window. The posting
adds the run stretches as time logs on the Job Card, with the good quantity as completed quantity,
and adds the scrap to the Job Card's process loss.

The last roll-up is remembered by the outbox itself: the newest production-log posting for the
machine and job card says where the next window starts, so nothing about ERPNext is stored on the
Machine. A window with no counts and no run time queues nothing.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import get_datetime, now_datetime

from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed
from foames.foames_adapters.erpnext.production import production_payload, running_intervals, window_key
from foames.foames_adapters.machine_window import counter_totals, state_before, state_events

OPERATION = "Job Card Production Log"


def rollup_enabled() -> bool:
	if not erpnext_installed():
		return False
	settings = frappe.get_cached_doc("ERPNext Adapter Settings")
	return bool(settings.enable_postings and settings.roll_up_counts_to_job_cards)


def job_card_for_reference(reference: str | None) -> str | None:
	"""The ERPNext Job Card an External Reference points at, or None for any other reference."""
	if not reference:
		return None
	row = frappe.db.get_value(
		"External Reference", reference, ["erp_system", "reference_type", "external_id"], as_dict=True
	)
	if not row or row.erp_system != ADAPTER_KEY or row.reference_type != "Job Card":
		return None
	return row.external_id


def last_window_end(machine: str, job_card: str):
	"""Where the previous roll-up of this machine and job card stopped, whatever its status."""
	rows = frappe.get_all(
		"ERPNext Outbox",
		filters={
			"operation": OPERATION,
			"reference_doctype": "Machine",
			"reference_name": machine,
			"status": ("!=", "Cancelled"),
		},
		fields=["payload"],
		order_by="creation desc",
		limit_page_length=20,
	)
	for row in rows:
		try:
			payload = json.loads(row.payload or "{}")
		except ValueError:
			continue
		if payload.get("job_card") == job_card and payload.get("to_time"):
			return get_datetime(payload["to_time"])
	return None


def roll_up(machine, job_card: str | None = None, until=None, since=None) -> str | None:
	"""Queue the production of one machine since its last roll-up. Returns the outbox name, or
	None when there was nothing to roll up.

	`job_card` and `since` default to the machine's current job; `on_job_changed` passes the job
	that just ended instead.
	"""
	if isinstance(machine, str):
		machine = frappe.get_doc("Machine", machine)
	if job_card is None:
		job_card = job_card_for_reference(machine.current_job_reference)
		since = since or machine.current_job_since
	if not job_card:
		return None
	start = last_window_end(machine.name, job_card) or (get_datetime(since) if since else None)
	if not start:
		return None
	end = get_datetime(until) if until else now_datetime()
	if end <= start:
		return None

	totals = counter_totals(machine.name, start, end)
	intervals = running_intervals(
		state_before(machine.name, start), state_events(machine.name, start, end), start, end
	)
	payload = production_payload(job_card, start, end, totals, intervals, machine.name)
	if payload is None:
		return None
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue

	return enqueue(
		OPERATION,
		payload,
		window_key(job_card, machine.name, end),
		sequence_group=job_card,
		reference_doctype="Machine",
		reference_name=machine.name,
	)


def roll_up_all() -> list[str]:
	"""Scheduled every few minutes: roll up every enabled machine that has a current job."""
	if not rollup_enabled():
		return []
	queued = []
	for name in frappe.get_all(
		"Machine", {"disabled": 0, "current_job_reference": ("is", "set")}, pluck="name", order_by="name"
	):
		try:
			posting = roll_up(name)
		except Exception:
			frappe.log_error(title=f"Job Card roll-up for {name}")
			continue
		if posting:
			queued.append(posting)
	return queued


def on_job_changed(machine, previous_reference: str | None, at):
	"""Registered under `foames_machine_job_changed`: close the books on the job that ended, up to
	the moment the job changed, so the new job starts with a clean window. The hook runs inside
	the Machine's save, so the record before the save still says when the old job started."""
	if not rollup_enabled():
		return
	job_card = job_card_for_reference(previous_reference)
	if not job_card:
		return
	before = machine.get_doc_before_save()
	since = before.current_job_since if before else None
	roll_up(machine, job_card=job_card, until=at, since=since)


def mark_current_job_cards(snapshot: dict, since, now):
	"""Registered under `foames_floor_snapshot_extensions`: say which of a machine's open Job Cards
	it is working on, and whether that card is still open in ERPNext."""
	if not erpnext_installed():
		return
	for m in snapshot.get("machines", []):
		job = m.get("current_job")
		if not job or job.get("erp_system") != ADAPTER_KEY:
			continue
		job_card = job.get("external_id")
		job["docstatus"] = frappe.db.get_value("Job Card", job_card, "docstatus")
		job["open"] = job["docstatus"] == 0
		for jc in m.get("job_cards") or []:
			jc["current"] = jc.get("name") == job_card


def current_job_card_not_open(snapshot: dict) -> list[dict]:
	"""Registered under `foames_suggestion_rules`: a machine still assigned to a Job Card that is
	submitted, cancelled or gone keeps producing counts nobody rolls up."""
	out = []
	for m in snapshot.get("machines", []):
		job = m.get("current_job")
		if not job or job.get("erp_system") != ADAPTER_KEY or job.get("open", True):
			continue
		out.append(
			{
				"rule_key": f"erpnext-job-card-closed:{m['name']}:{job.get('external_id')}",
				"category": "ERP",
				"severity": "Warning",
				"title": f"{m['name']} is assigned to Job Card {job.get('external_id')}, which is no longer open",
				"suggestion": (
					f"Machine {m['name']} still names Job Card {job.get('external_id')} as its current job, but "
					"that Job Card is submitted, cancelled or deleted in ERPNext. Its counts cannot be rolled up. "
					"Set the machine's next job, or clear the current job."
				),
				"reference_doctype": "Machine",
				"reference_name": m["name"],
				"evidence": {"job_card": job.get("external_id"), "docstatus": job.get("docstatus")},
			}
		)
	return out
