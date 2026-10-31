# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The arithmetic of rolling machine data up to an ERP job: which stretches of a window the
machine ran, and what the window produced. No Frappe dependency; the roll-up module feeds it
events it has read and queues what it returns.
"""

from __future__ import annotations

from datetime import datetime

from foames.foames_mes.counters import good_and_scrap


def running_intervals(
	state_before: str | None, events: list[tuple[datetime, str]], start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
	"""The [from, to) stretches inside [start, end) during which the machine was Running.

	`state_before` is the state carried into the window and `events` the (timestamp, state)
	changes inside it, in time order. An interval still open at `end` is clipped there.
	"""
	intervals: list[tuple[datetime, datetime]] = []
	state, cursor = state_before, start
	for at, new_state in events:
		if at <= start:
			state = new_state
			continue
		if at >= end:
			break
		if state == "Running" and at > cursor:
			intervals.append((cursor, at))
		state, cursor = new_state, at
	if state == "Running" and end > cursor:
		intervals.append((cursor, end))
	return intervals


def production_payload(
	job_card: str,
	start: datetime,
	end: datetime,
	totals: dict[str, float],
	intervals: list[tuple[datetime, datetime]],
	machine: str,
) -> dict | None:
	"""The Job Card Production Log payload for a window, or None when the window has nothing to
	report (no production and no run time), so an idle machine queues nothing."""
	good, scrap = good_and_scrap(totals)
	run_minutes = sum((b - a).total_seconds() for a, b in intervals) / 60.0
	if good <= 0 and scrap <= 0 and run_minutes <= 0:
		return None
	payload = {
		"job_card": job_card,
		"from_time": start.isoformat(sep=" ", timespec="seconds"),
		"to_time": end.isoformat(sep=" ", timespec="seconds"),
		"completed_qty": good,
		"process_loss_qty": scrap,
		"run_intervals": [
			[a.isoformat(sep=" ", timespec="seconds"), b.isoformat(sep=" ", timespec="seconds")]
			for a, b in intervals
		],
		"remarks": f"Machine {machine}: {good:g} good, {scrap:g} scrap, {run_minutes:.1f} min running",
	}
	return payload


def window_key(job_card: str, machine: str, end: datetime) -> str:
	"""Idempotency key of a window: a window that ends at the same moment is the same window."""
	return f"{job_card}:{machine}:production:{end.isoformat(sep=' ', timespec='seconds')}"
