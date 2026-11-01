# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Rolls each machine's counts and run time up to the S/4HANA order operation it is working on.

A Machine names its job through `current_job_reference`, an External Reference of type Job Card.
On S/4HANA that reference is an order operation, `ORDER|OPERATION`. Every few minutes
(`roll_up_all`, from the scheduler) and whenever the job changes (`on_job_changed`, from the core's
`foames_machine_job_changed` hook) the adapter takes the window since the last roll-up, sums the
good and scrap counter deltas in it, finds the stretches the machine was Running, and queues one
partial confirmation for the window through the S4HANA Outbox: yield, scrap, optionally the
machine time as an activity, and the window as execution start and end.

The last roll-up is remembered by the outbox itself: the newest confirmation queued for the
machine and operation says, through its execution end, where the next window starts, so nothing
about S/4HANA is stored on the Machine. A window with nothing to report queues nothing. Every
confirmation of one order shares the order as sequence group, so they reach S/4HANA in order and a
rejected one (a locked order, a closed period) holds the rest until it is fixed.
"""

from __future__ import annotations

import json

import frappe
from frappe.query_builder import Order
from frappe.utils import get_datetime, now_datetime

from foames.foames_adapters.erpnext.production import running_intervals
from foames.foames_adapters.machine_window import counter_totals, state_before, state_events
from foames.foames_adapters.s4hana import confirmations
from foames.foames_adapters.s4hana.adapter import ADAPTER_KEY, JOB_CARD
from foames.foames_adapters.s4hana.production import (
	STANDARD_SEQUENCE,
	RollUpOptions,
	confirmation_payload,
	normal_sequence,
	parse_job,
	window_end,
	window_key,
)

OPERATIONS = (confirmations.PRODUCTION, confirmations.PROCESS)


def settings():
	from foames.foames_adapters.doctype.s4hana_settings.s4hana_settings import get_settings

	return get_settings()


def rollup_enabled() -> bool:
	s = settings()
	return bool(s.enabled and s.base_url and s.roll_up_counts_to_confirmations)


def options_from_settings(s=None) -> RollUpOptions:
	s = s or settings()
	return RollUpOptions(
		unit=(s.confirmation_unit or "").strip(),
		process_order=bool(s.confirm_process_orders),
		activity_position=int(s.machine_time_activity_position or 0),
		activity_unit=(s.machine_time_unit or "MIN").strip(),
		no_goods_movements=bool(s.confirm_without_goods_movements),
	)


def job_for_reference(reference: str | None) -> tuple[str, str, str] | None:
	"""The (order, operation, sequence) an External Reference points at, or None for any other
	reference. An operation S/4HANA already said does not exist is None too: its confirmations would
	only fail and hold the rest of the order. An Unverified one (S/4HANA was unreachable) is used."""
	if not reference:
		return None
	row = frappe.db.get_value(
		"External Reference",
		reference,
		["erp_system", "reference_type", "external_id", "status"],
		as_dict=True,
	)
	if not row or row.erp_system != ADAPTER_KEY or row.reference_type != JOB_CARD or row.status == "Missing":
		return None
	try:
		return parse_job(row.external_id)
	except ValueError:
		return None


def last_window_end(machine: str, order: str, operation: str, sequence: str = STANDARD_SEQUENCE):
	"""Where the previous roll-up of this machine and operation stopped, whatever its status. A
	cancelled window counts too: cancelling drops its production, it does not hand it to the next
	window. The read locks the rows, so it sees a window another worker has just committed."""
	outbox = frappe.qb.DocType("S4HANA Outbox")
	rows = (
		frappe.qb.from_(outbox)
		.select(outbox.payload)
		.where(
			outbox.operation.isin(OPERATIONS)
			& (outbox.reference_doctype == "Machine")
			& (outbox.reference_name == machine)
		)
		.orderby(outbox.creation, order=Order.desc)
		.limit(20)
		.for_update()
		.run(as_dict=True)
	)
	for row in rows:
		try:
			payload = json.loads(row.payload or "{}")
		except ValueError:
			continue
		if (
			payload.get("OrderID") == order
			and payload.get("OrderOperation") == operation
			and normal_sequence(payload.get("Sequence")) == sequence
		):
			end = window_end(payload)
			if end:
				return end
	return None


def roll_up(machine, job: tuple[str, str, str] | None = None, until=None, since=None) -> str | None:
	"""Queue the production of one machine since its last roll-up. Returns the outbox name, or
	None when there was nothing to roll up.

	`job` and `since` default to the machine's current job; `on_job_changed` passes the job that
	just ended instead.
	"""
	if isinstance(machine, str):
		machine = frappe.get_doc("Machine", machine)
	if job is None:
		job = job_for_reference(machine.current_job_reference)
		since = since or machine.current_job_since
	if not job:
		return None
	order, operation, sequence = job
	# One roll-up per machine at a time: the scheduler and a job change must not both cut a window
	# from the same checkpoint. A job change already holds this lock through the Machine's save.
	frappe.db.get_value("Machine", machine.name, "name", for_update=True)
	start = last_window_end(machine.name, order, operation, sequence) or (
		get_datetime(since) if since else None
	)
	if not start:
		return None
	# Execution times reach S/4HANA in whole seconds, so windows are cut on whole seconds too.
	start = start.replace(microsecond=0)
	end = (get_datetime(until) if until else now_datetime()).replace(microsecond=0)
	if end <= start:
		return None

	totals = counter_totals(machine.name, start, end)
	intervals = running_intervals(
		state_before(machine.name, start), state_events(machine.name, start, end), start, end
	)
	options = options_from_settings()
	payload = confirmation_payload(order, operation, start, end, totals, intervals, options, sequence)
	if payload is None:
		return None
	from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue

	return enqueue(
		options.operation,
		payload,
		window_key(order, operation, machine.name, end, sequence),
		sequence_group=order,
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
			frappe.log_error(title=f"S/4HANA confirmation roll-up for {name}")
			continue
		if posting:
			queued.append(posting)
	return queued


def on_job_changed(machine, previous_reference: str | None, at):
	"""Registered under `foames_machine_job_changed`: close the books on the operation that ended,
	up to the moment the job changed, so the new job starts with a clean window. The hook runs
	inside the Machine's save, so the record before the save still says when the old job started."""
	if not rollup_enabled():
		return
	job = job_for_reference(previous_reference)
	if not job:
		return
	before = machine.get_doc_before_save()
	since = before.current_job_since if before else None
	roll_up(machine, job=job, until=at, since=since)


def confirmation_rejected(snapshot: dict) -> list[dict]:
	"""Registered under `foames_suggestion_rules`: a machine whose roll-up confirmations S/4HANA
	rejected. Until the failed one is fixed and requeued, or cancelled, every later confirmation of
	the order waits behind it, so the counts never reach S/4HANA. A machine that has since left the
	job is included: the confirmation that closed its job can be the one that failed."""
	if not rollup_enabled():
		return []
	machines = [m["name"] for m in snapshot.get("machines", [])]
	if not machines:
		return []
	failed = frappe.get_all(
		"S4HANA Outbox",
		filters={
			"operation": ("in", OPERATIONS),
			"reference_doctype": "Machine",
			"reference_name": ("in", machines),
			"status": "Failed",
		},
		fields=["name", "reference_name", "sequence_group", "last_error"],
		order_by="creation asc",
	)
	out, seen = [], set()
	for row in failed:
		if row.reference_name in seen:
			continue
		seen.add(row.reference_name)
		out.append(
			{
				"rule_key": f"s4hana-confirmation-failed:{row.reference_name}:{row.name}",
				"category": "ERP",
				"severity": "Warning",
				"title": f"S/4HANA rejected a confirmation of {row.reference_name} for order {row.sequence_group}",
				"suggestion": (
					f"S/4HANA rejected the roll-up confirmation {row.name} of machine {row.reference_name}: "
					f"{row.last_error or 'no message'}. Later confirmations of order {row.sequence_group} wait "
					"behind it. Fix the cause in S/4HANA (a locked order, a closed posting period, a wrong unit), "
					"then requeue the posting, or cancel it."
				),
				"reference_doctype": "S4HANA Outbox",
				"reference_name": row.name,
				"evidence": {
					"machine": row.reference_name,
					"order": row.sequence_group,
					"last_error": row.last_error,
				},
			}
		)
	return out
