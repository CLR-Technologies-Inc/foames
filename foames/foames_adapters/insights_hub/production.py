# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The arithmetic of rolling machine data up to Insights Hub: what a window produced, and the time
series record and events that report it. No Frappe dependency; `rollup.py` feeds it the counts and
run stretches it has read and queues what it returns.

Opcenter Intelligence reads production from the platform's time series. Each roll-up writes one
record at the window's end on an aspect of the machine's asset: the good and scrap counts in the
window, the minutes the machine was Running, and the job it was working on. The aspect's variables
are named here and created once on the tenant (see the adapter guide); a site that uses other names
renames them in Insights Hub Settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, tzinfo

from foames.foames_adapters.insights_hub.outbox import (
	SEVERITY_ERROR,
	SEVERITY_INFORMATION,
	SEVERITY_WARNING,
	iso_utc,
	parse_time,
)
from foames.foames_mes.counters import good_and_scrap

DEFAULT_PROPERTY_SET = "FoaMESProduction"
# The aspect's variables, as FoaMES names them by default.
DEFAULT_VARIABLES = {
	"good": "goodCount",
	"scrap": "scrapCount",
	"run_minutes": "runMinutes",
	"window_minutes": "windowMinutes",
	"job": "job",
	"state": "state",
}

# Which states are worth an event, and how serious the standard event type should call them.
STATE_SEVERITY = {
	"Down": SEVERITY_ERROR,
	"Unknown": SEVERITY_WARNING,
	"Setup": SEVERITY_INFORMATION,
	"Idle": SEVERITY_INFORMATION,
	"Running": SEVERITY_INFORMATION,
}


@dataclass
class RollUpOptions:
	"""How a window becomes a time series record, from Insights Hub Settings."""

	property_set: str = DEFAULT_PROPERTY_SET
	variables: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VARIABLES))
	# The site's timezone: Machine Events carry naive site-local timestamps, Insights Hub wants UTC.
	tz: tzinfo | None = None

	def variable(self, key: str) -> str:
		return self.variables.get(key) or DEFAULT_VARIABLES[key]


def to_utc_iso(moment: datetime, tz: tzinfo | None) -> str:
	if moment.tzinfo is None and tz is not None:
		moment = moment.replace(tzinfo=tz)
	return iso_utc(moment)


def timeseries_payload(
	entity_id: str,
	start: datetime,
	end: datetime,
	totals: dict[str, float],
	intervals: list[tuple[datetime, datetime]],
	options: RollUpOptions,
	job: str | None = None,
	state: str | None = None,
) -> dict | None:
	"""The time series write for a window, or None when the window has nothing to report.

	Good counts and scrap counts come from the counter deltas, running minutes from the Running
	stretches. A window with no counts and no run time queues nothing: an idle machine is not
	production, and Opcenter Intelligence takes the absence of a record as nothing produced. The
	window's own length is sent too, so a reader can tell a short window from a slow machine.
	"""
	good, scrap = good_and_scrap(totals)
	run_minutes = round(sum((b - a).total_seconds() for a, b in intervals) / 60.0, 3)
	if good <= 0 and scrap <= 0 and run_minutes <= 0:
		return None
	record = {
		"_time": to_utc_iso(end, options.tz),
		options.variable("good"): good,
		options.variable("scrap"): scrap,
		options.variable("run_minutes"): run_minutes,
		options.variable("window_minutes"): round((end - start).total_seconds() / 60.0, 3),
	}
	if job:
		record[options.variable("job")] = job
	if state:
		record[options.variable("state")] = state
	return {"entityId": entity_id, "propertySetName": options.property_set, "data": [record]}


def window_end(payload: dict, tz: tzinfo | None = None) -> datetime | None:
	"""Where a roll-up's window ended, read back from its record's `_time`, in the site's timezone
	as a naive datetime (the form Machine Events use)."""
	times = [parse_time(record.get("_time")) for record in payload.get("data") or []]
	times = [t for t in times if t is not None]
	if not times:
		return None
	end = max(times)
	if tz is not None:
		end = end.astimezone(tz)
	return end.replace(tzinfo=None)


def window_key(machine: str, end: datetime) -> str:
	"""Idempotency key of a window: a window that ends at the same moment is the same window."""
	return f"{machine}:timeseries:{end.isoformat(sep=' ', timespec='seconds')}"


def state_event_payload(
	entity_id: str, machine: str, state: str, previous_state: str | None, at: datetime, tz: tzinfo | None
) -> dict:
	"""An event on the machine's asset for a state change, in the platform's standard event type."""
	description = f"{machine} is {state}"
	if previous_state:
		description += f" (was {previous_state})"
	return {
		"entityId": entity_id,
		"timestamp": to_utc_iso(at, tz),
		"severity": STATE_SEVERITY.get(state, SEVERITY_INFORMATION),
		"description": description,
		"code": f"FOAMES.STATE.{state.upper()}",
		"source": "FoaMES",
		"acknowledged": False,
	}


def state_key(machine: str, state: str, at: datetime) -> str:
	return f"{machine}:state:{state}:{at.isoformat(sep=' ', timespec='seconds')}"
