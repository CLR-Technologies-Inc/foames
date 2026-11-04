# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Quality Inspections for ERPNext from what the floor measured.

A machine's Measurement events (a gauge, a scale, an inline sensor) are the readings a Quality
Inspection asks for, as long as the measurement is named like the ERPNext Quality Inspection
Parameter it stands for. `measurement_readings` turns the events of a window into the readings a
`Quality Inspection` posting takes (the last ten values per parameter, in time order), and
`queue_inspection` queues the posting; `post_inspection_from_measurements` in `api.py` does both
for an agent or a gateway. ERPNext judges the readings against the template's limits.
"""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import get_datetime, now_datetime

from foames.foames_adapters.erpnext.postings import MAX_READINGS_PER_SPECIFICATION


def measurement_readings(
	machine: str,
	since,
	until=None,
	specifications: list[str] | None = None,
	per_specification: int = MAX_READINGS_PER_SPECIFICATION,
) -> list[dict]:
	"""The readings for a Quality Inspection from a machine's Measurement events between `since`
	and `until` (default now): one entry per measurement name (or per name in `specifications`,
	in that order), with the last `per_specification` values in time order. Only those last values
	are read from the database, however dense the sensor."""
	event = frappe.qb.DocType("Machine Event")
	window = (
		(event.machine == machine)
		& (event.event_type == "Measurement")
		& (event.timestamp >= get_datetime(since))
		& (event.timestamp <= get_datetime(until) if until is not None else now_datetime())
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
	readings: list[dict],
	idempotency_key: str | None = None,
	source: tuple | None = None,
	**extra,
) -> tuple[str, bool]:
	"""Queue a `Quality Inspection` posting for a Job Card or Stock Entry. Without a key, the
	business event is the readings for the document plus their `source` (the machine and the window
	they were read from): the same call queues once, and a later window of the same gauge, even
	with identical values, is a new inspection."""
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue_posting

	payload = {
		"reference_type": reference_type,
		"reference_name": reference_name,
		"readings": readings,
		**extra,
	}
	if not idempotency_key:
		digest = hashlib.sha256(
			json.dumps([readings, list(source or [])], sort_keys=True, default=str).encode()
		).hexdigest()[:12]
		idempotency_key = f"inspection:{reference_type}:{reference_name}:{digest}"
	group = f"{reference_type}:{reference_name}"
	return enqueue_posting("Quality Inspection", payload, idempotency_key, group, None, None)
