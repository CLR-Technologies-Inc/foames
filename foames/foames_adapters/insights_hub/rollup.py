# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Rolls each machine's counts and run time up to its Insights Hub asset, where Opcenter
Intelligence reads them.

A Machine names its asset through `workstation_reference`, an External Reference of type
Workstation on the Insights Hub adapter whose External ID is the asset id. Every few minutes
(`roll_up_all`, from the scheduler) and whenever the machine's job changes (`on_job_changed`, from
the core's `foames_machine_job_changed` hook) the adapter takes the window since the last roll-up,
sums the good and scrap counter deltas in it, finds the stretches the machine was Running, and queues
one time series record at the window's end through the Insights Hub Outbox, tagged with the job the
machine was on. With **Send State Changes as Events** on, each state change also queues an event on
the asset (`on_state_changed`, from `foames_machine_state_changed`).

The last roll-up is remembered by the outbox itself: the newest record queued for the machine says,
through its `_time`, where the next window starts, so nothing about Insights Hub is stored on the
Machine. A window with nothing to report queues nothing. A machine that has never been rolled up
starts with the last few minutes, so a tenant that is connected to a plant with months of history
is not flooded with it.
"""

from __future__ import annotations

import json
from datetime import timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe.query_builder import Order
from frappe.utils import get_datetime, now_datetime

from foames.foames_adapters.erpnext.production import running_intervals
from foames.foames_adapters.insights_hub import ADAPTER_KEY
from foames.foames_adapters.insights_hub.adapter import JOB_CARD
from foames.foames_adapters.insights_hub.outbox import EVENT, TIME_SERIES
from foames.foames_adapters.insights_hub.production import (
	RollUpOptions,
	state_event_payload,
	state_key,
	timeseries_payload,
	window_end,
	window_key,
)
from foames.foames_adapters.machine_window import counter_totals, state_before, state_events

WORKSTATION = "Workstation"
FIRST_WINDOW_MINUTES = 10


def settings():
	from foames.foames_adapters.doctype.insights_hub_settings.insights_hub_settings import get_settings

	return get_settings()


def rollup_enabled() -> bool:
	s = settings()
	return bool(s.enabled and s.gateway_url and s.send_machine_data)


def events_enabled() -> bool:
	s = settings()
	return bool(s.enabled and s.gateway_url and s.send_state_events)


def site_timezone():
	try:
		from frappe.utils import get_system_timezone

		name = get_system_timezone()
	except ImportError:  # older Frappe
		name = frappe.db.get_single_value("System Settings", "time_zone")
	try:
		return ZoneInfo(name) if name else None
	except Exception:
		return None


def options_from_settings(s=None) -> RollUpOptions:
	s = s or settings()
	return s.rollup_options(site_timezone())


def asset_for_reference(reference: str | None) -> str | None:
	"""The asset id an External Reference points at, or None for any other reference. An asset
	Insights Hub already said does not exist is None too; an Unverified one is used."""
	if not reference:
		return None
	row = frappe.db.get_value(
		"External Reference",
		reference,
		["erp_system", "reference_type", "external_id", "status"],
		as_dict=True,
	)
	if (
		not row
		or row.erp_system != ADAPTER_KEY
		or row.reference_type != WORKSTATION
		or row.status == "Missing"
	):
		return None
	return (row.external_id or "").strip() or None


def job_tag(reference: str | None) -> str | None:
	"""What the roll-up writes as the machine's job: the External ID of its current job reference,
	whichever ERP it points at. Opcenter Intelligence correlates production to orders by that tag,
	so an S/4HANA or ERPNext order number is as good as an Insights Hub one."""
	if not reference:
		return None
	row = frappe.db.get_value(
		"External Reference", reference, ["erp_system", "reference_type", "external_id"], as_dict=True
	)
	if not row or not row.external_id:
		return None
	if row.erp_system == ADAPTER_KEY and row.reference_type == JOB_CARD:
		return row.external_id
	return f"{row.erp_system}:{row.external_id}"


def last_window_end(machine: str, tz):
	"""Where the previous roll-up of this machine stopped, whatever its status. A cancelled window
	counts too: cancelling drops its production, it does not hand it to the next window. The read
	locks the rows, so it sees a window another worker has just committed."""
	outbox = frappe.qb.DocType("Insights Hub Outbox")
	rows = (
		frappe.qb.from_(outbox)
		.select(outbox.payload)
		.where(
			(outbox.operation == TIME_SERIES)
			& (outbox.reference_doctype == "Machine")
			& (outbox.reference_name == machine)
		)
		.orderby(outbox.creation, order=Order.desc)
		.limit(1)
		.for_update()
		.run(as_dict=True)
	)
	for row in rows:
		try:
			payload = json.loads(row.payload or "{}")
		except ValueError:
			continue
		end = window_end(payload, tz)
		if end:
			return end
	return None


def roll_up(machine, until=None, since=None, job: str | None = None, state: str | None = None) -> str | None:
	"""Queue the production of one machine since its last roll-up. Returns the outbox name, or
	None when there was nothing to roll up."""
	if isinstance(machine, str):
		machine = frappe.get_doc("Machine", machine)
	asset = asset_for_reference(machine.workstation_reference)
	if not asset:
		return None
	if job is None:
		job = job_tag(machine.current_job_reference)
	# One roll-up per machine at a time: the scheduler and a job change must not both cut a window
	# from the same checkpoint. A job change already holds this lock through the Machine's save.
	frappe.db.get_value("Machine", machine.name, "name", for_update=True)
	options = options_from_settings()
	end = (get_datetime(until) if until else now_datetime()).replace(microsecond=0)
	start = last_window_end(machine.name, options.tz)
	if not start:
		start = get_datetime(since) if since else end - timedelta(minutes=FIRST_WINDOW_MINUTES)
	start = start.replace(microsecond=0)
	if end <= start:
		return None

	totals = counter_totals(machine.name, start, end)
	intervals = running_intervals(
		state_before(machine.name, start), state_events(machine.name, start, end), start, end
	)
	payload = timeseries_payload(asset, start, end, totals, intervals, options, job=job, state=state)
	if payload is None:
		return None
	from foames.foames_adapters.doctype.insights_hub_outbox.insights_hub_outbox import enqueue

	return enqueue(
		TIME_SERIES,
		payload,
		window_key(machine.name, end),
		reference_doctype="Machine",
		reference_name=machine.name,
	)


def roll_up_all() -> list[str]:
	"""Scheduled every few minutes: roll up every enabled machine that points at an asset."""
	if not rollup_enabled():
		return []
	queued = []
	for row in frappe.get_all(
		"Machine",
		{"disabled": 0, "workstation_reference": ("is", "set")},
		fields=["name", "status"],
		order_by="name",
	):
		try:
			posting = roll_up(row.name, state=row.status)
		except Exception:
			frappe.log_error(title=f"Insights Hub roll-up for {row.name}")
			continue
		if posting:
			queued.append(posting)
	return queued


def on_job_changed(machine, previous_reference: str | None, at):
	"""Registered under `foames_machine_job_changed`: close the window on the job that ended, up to
	the moment the job changed, so the new job starts with a clean window and no record mixes two
	jobs. The hook runs inside the Machine's save, so the record before the save still says when the
	old job started."""
	if not rollup_enabled():
		return
	before = machine.get_doc_before_save()
	since = before.current_job_since if before else None
	roll_up(machine, until=at, since=since, job=job_tag(previous_reference) or "", state=machine.status)


def on_state_changed(machine, previous_state: str | None, state: str, at) -> str | None:
	"""Registered under `foames_machine_state_changed`: an event on the asset for each state change.
	Returns the outbox record queued, if any."""
	if not events_enabled():
		return None
	asset = asset_for_reference(machine.workstation_reference)
	if not asset or not state:
		return None
	at = get_datetime(at) or now_datetime()
	s = settings()
	payload = state_event_payload(asset, machine.name, state, previous_state, at, site_timezone())
	if (s.event_type_id or "").strip():
		payload["typeId"] = s.event_type_id.strip()
	from foames.foames_adapters.doctype.insights_hub_outbox.insights_hub_outbox import enqueue

	return enqueue(
		EVENT,
		payload,
		state_key(machine.name, state, at),
		sequence_group=f"asset:{asset}",
		reference_doctype="Machine",
		reference_name=machine.name,
	)


def posting_rejected(snapshot: dict) -> list[dict]:
	"""Registered under `foames_suggestion_rules`: a machine whose roll-up Insights Hub rejected.
	A rejected time series write usually means the aspect or a variable is missing on the asset, or
	the asset id is wrong; until it is fixed the machine's production does not reach Opcenter
	Intelligence."""
	s = settings()
	if not (s.enabled and s.gateway_url and (s.send_machine_data or s.send_state_events)):
		return []
	machines = [m["name"] for m in snapshot.get("machines", [])]
	if not machines:
		return []
	failed = frappe.get_all(
		"Insights Hub Outbox",
		filters={
			"operation": ("in", (TIME_SERIES, EVENT)),
			"reference_doctype": "Machine",
			"reference_name": ("in", machines),
			"status": "Failed",
		},
		fields=["name", "reference_name", "operation", "last_error"],
		order_by="creation asc",
	)
	out, seen = [], set()
	for row in failed:
		if row.reference_name in seen:
			continue
		seen.add(row.reference_name)
		out.append(
			{
				"rule_key": f"insights-hub-posting-failed:{row.reference_name}:{row.name}",
				"category": "ERP",
				"severity": "Warning",
				"title": f"Insights Hub rejected a {row.operation.lower()} of {row.reference_name}",
				"suggestion": (
					f"Insights Hub rejected the posting {row.name} of machine {row.reference_name}: "
					f"{row.last_error or 'no message'}. Check that the machine's Workstation reference is the "
					"asset id, that the asset has the aspect and variables named in Insights Hub Settings, and "
					"that the application is allowed to write to it. Then requeue the posting, or cancel it."
				),
				"reference_doctype": "Insights Hub Outbox",
				"reference_name": row.name,
				"evidence": {
					"machine": row.reference_name,
					"operation": row.operation,
					"last_error": row.last_error,
				},
			}
		)
	return out
