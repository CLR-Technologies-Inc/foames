# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Quality Inspections for ERPNext from what the floor measured.

A machine's Measurement events (a gauge, a scale, an inline sensor) are the readings a Quality
Inspection asks for, as long as the measurement is named like the ERPNext Quality Inspection
Parameter it stands for. `measurement_readings` turns the events of a window into the readings a
`Quality Inspection` posting takes (the last ten values per parameter, in time order), and
`queue_inspection` queues the posting; `post_inspection_from_measurements` in `api.py` does both
for an agent or a gateway. ERPNext judges the readings against the template's limits.

With **Inspect Job Cards from Machine Measurements** on, `on_job_changed` (registered under the
core's `foames_machine_job_changed` hook) does it on its own whenever a machine's job ends: the
readings of the job's window, for the parameters of the template the Job Card names.
"""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import get_datetime, now_datetime

from foames.foames_adapters.erpnext import erpnext_installed
from foames.foames_adapters.erpnext.postings import MAX_READINGS_PER_SPECIFICATION


def measurement_readings(
	machine: str,
	since,
	until=None,
	specifications: list[str] | None = None,
	per_specification: int = MAX_READINGS_PER_SPECIFICATION,
	until_inclusive: bool = True,
) -> list[dict]:
	"""The readings for a Quality Inspection from a machine's Measurement events between `since`
	and `until` (default now; excluded with `until_inclusive=False`, for windows that abut the next
	job's): one entry per measurement name (or per name in `specifications`, in that order), with
	the last `per_specification` values in time order. Only those last values are read from the
	database, however dense the sensor."""
	event = frappe.qb.DocType("Machine Event")
	end = get_datetime(until) if until is not None else now_datetime()
	window = (
		(event.machine == machine)
		& (event.event_type == "Measurement")
		& (event.timestamp >= get_datetime(since))
		& (event.timestamp <= end if until_inclusive else event.timestamp < end)
		& event.value.isnotnull()
	)
	if specifications:
		names = list(dict.fromkeys(specifications))
	else:
		names = (
			frappe.qb.from_(event)
			.select(event.measurement_name)
			.distinct()
			.where(window)
			.orderby(event.measurement_name)
			.run(pluck=True)
		)
	limit = max(int(per_specification), 1)
	readings = []
	for name in names:
		latest = (
			frappe.qb.from_(event)
			.select(event.value)
			.where(window & (event.measurement_name == name))
			.orderby(event.timestamp, order=frappe.qb.desc)
			.orderby(event.name, order=frappe.qb.desc)
			.limit(limit)
			.run(pluck=True)
		)
		if latest:
			readings.append({"specification": name, "values": [float(v) for v in reversed(latest)]})
	return readings


def queue_inspection(
	reference_type: str,
	reference_name: str,
	readings: list[dict] | None,
	idempotency_key: str | None = None,
	source: tuple | None = None,
	measurements: dict | None = None,
	not_before=None,
	**extra,
) -> tuple[str, bool]:
	"""Queue a `Quality Inspection` posting for a Job Card or Stock Entry, with `readings`, or with
	`measurements` (machine, since, until, specifications) that are read when the posting is
	performed, from `not_before` on. Without a key, the business event is the readings for the
	document plus their `source` (the machine and the window they were read from), or the
	measurement window: the same call queues once, and a later window of the same gauge, even with
	identical values, is a new inspection."""
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue_posting

	payload = {"reference_type": reference_type, "reference_name": reference_name, **extra}
	if measurements:
		payload["measurements"] = measurements
		basis = ["measurements", measurements]
	else:
		payload["readings"] = readings
		basis = [readings, list(source or [])]
	if not idempotency_key:
		digest = hashlib.sha256(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:12]
		idempotency_key = f"inspection:{reference_type}:{reference_name}:{digest}"
	group = f"{reference_type}:{reference_name}"
	return enqueue_posting("Quality Inspection", payload, idempotency_key, group, None, None, not_before)


def inspection_on_job_change_enabled() -> bool:
	if not erpnext_installed():
		return False
	settings = frappe.get_cached_doc("ERPNext Adapter Settings")
	return bool(settings.enable_postings and settings.inspect_job_cards_from_measurements)


def inspect_job_card(machine: str, job_card: str, since, until, submit: bool | None = None):
	"""Queue a Quality Inspection for `job_card` from the measurements `machine` took from `since`
	up to (not including) `until`, for the parameters of the template the Job Card's operation (or
	its BOM, or its item) names; other measurements are left out, so a gauge the template does not
	ask about cannot fail the inspection. The readings are taken when the posting is performed,
	after the settings' **Wait for Late Measurements**, so a reading a gateway delivers late still
	counts; a window that turns out empty posts nothing. Unless `submit` says, the inspection is
	submitted only when every parameter of the template was measured; otherwise it is left as a
	draft for a person to finish. Returns `(outbox name, created)`, or None when the Job Card is
	gone or names no template."""
	from frappe.utils import add_to_date

	from foames.foames_adapters.erpnext.executor import inspection_subject, template_criteria

	if not frappe.db.exists("Job Card", job_card):
		return None
	card = frappe.get_doc("Job Card", job_card)
	_item, _bom, template = inspection_subject(card, None)
	specifications = list(template_criteria(template)) if template else []
	if not specifications:
		return None
	since, until = get_datetime(since), get_datetime(until)
	if until <= since:
		return None
	delay = frappe.db.get_single_value("ERPNext Adapter Settings", "inspection_delay_minutes") or 0
	extra = {} if submit is None else {"submit": bool(submit)}
	return queue_inspection(
		"Job Card",
		job_card,
		None,
		measurements={
			"machine": machine,
			"since": str(since),
			"until": str(until),
			"specifications": specifications,
		},
		not_before=add_to_date(now_datetime(), minutes=int(delay)) if int(delay) > 0 else None,
		**extra,
	)


def on_job_changed(machine, previous_reference: str | None, at):
	"""Registered under `foames_machine_job_changed`: the job that ended gets its inspection from
	what the machine measured while it ran. The hook runs inside the Machine's save, so the record
	before the save still says when that job started; a Job Card that is gone is nothing to
	inspect, not a reason to refuse the machine its next job."""
	if not inspection_on_job_change_enabled() or machine.flags.get("skip_job_postings"):
		return
	from foames.foames_adapters.erpnext.rollup import job_card_for_reference

	job_card = job_card_for_reference(previous_reference)
	if not job_card:
		return
	before = machine.get_doc_before_save()
	since = before.current_job_since if before else None
	if not since:
		return
	inspect_job_card(machine.name, job_card, since, at)
