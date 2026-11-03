# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Preventive maintenance as pure arithmetic: how far a plan is through its interval, when it falls
due, and the suggestions a due plan raises. No Frappe dependency.

A plan is triggered by one meter:

- Calendar: days since the last service.
- Run Hours: Running time since the last service, from the same state ledger OEE uses, so Unknown,
  Idle, Setup and Down time never wear the machine on paper.
- Count: production since the last service, from the stored counter deltas (good plus scrap unless
  the plan names one counter), so a counter reset never looks like wear.

The meter is compared with the plan's interval. Below the warning share the plan is OK; from the
warning share to the interval it is Due Soon; from the interval to the interval plus the grace share
it is Due; past that it is Overdue.
"""

from __future__ import annotations

from datetime import datetime, timedelta

TRIGGERS = ("Calendar", "Run Hours", "Count")
UNITS = {"Calendar": "days", "Run Hours": "run hours", "Count": "counts"}
STATUSES = ("OK", "Due Soon", "Due", "Overdue")
DEFAULT_WARN_PERCENT = 90.0
DEFAULT_GRACE_PERCENT = 10.0
SEVERITY = {"Due Soon": "Info", "Due": "Warning", "Overdue": "Critical"}


def assess(
	used: float,
	interval: float,
	warn_percent: float | None = DEFAULT_WARN_PERCENT,
	grace_percent: float | None = DEFAULT_GRACE_PERCENT,
) -> dict:
	"""Status, percent of the interval used and what remains, for a meter reading against an interval."""
	if not interval or interval <= 0:
		raise ValueError("the interval must be positive")
	warn = DEFAULT_WARN_PERCENT if warn_percent is None else warn_percent
	grace = DEFAULT_GRACE_PERCENT if grace_percent is None else grace_percent
	used = max(float(used or 0), 0.0)
	percent = used / interval * 100.0
	if percent >= 100.0 + grace:
		status = "Overdue"
	elif percent >= 100.0:
		status = "Due"
	elif percent >= warn:
		status = "Due Soon"
	else:
		status = "OK"
	return {"status": status, "percent": percent, "remaining": interval - used}


def projected_due(
	used: float, interval: float, since: datetime, now: datetime, trigger: str = "Count"
) -> datetime | None:
	"""When the meter is expected to reach the interval.

	Calendar plans fall due exactly one interval after the last service. Usage plans are projected
	at the average rate since the last service; with no usage yet there is no projection.
	"""
	if trigger == "Calendar":
		return since + timedelta(days=interval)
	if used >= interval:
		return now
	elapsed = (now - since).total_seconds()
	if used <= 0 or elapsed <= 0:
		return None
	seconds_left = (interval - used) * elapsed / used
	return now + timedelta(seconds=seconds_left)


def calendar_days(since: datetime, now: datetime) -> float:
	return max((now - since).total_seconds() / 86400.0, 0.0)


def rule_key(plan: str, since, status: str) -> str:
	"""One suggestion per plan, service cycle and status, so a plan that moves from Due Soon to
	Overdue raises each step once and the next cycle starts afresh."""
	return f"maintenance:{plan}:{since}:{status}"


def findings(plans: list[dict]) -> list[dict]:
	"""Agent Suggestion dicts for plans that are Due Soon, Due or Overdue.

	Each plan dict carries name, title, machine, trigger, interval, used, percent, status, since and,
	when known, due_on and open_work_order.
	"""
	out = []
	for p in plans:
		status = p.get("status")
		if status not in SEVERITY:
			continue
		unit = UNITS.get(p.get("trigger"), "")
		used, interval = p.get("used") or 0, p.get("interval") or 0
		title = p.get("title") or p["name"]
		when = f" It is projected due on {p['due_on']}." if p.get("due_on") and status == "Due Soon" else ""
		if p.get("open_work_order"):
			action = f"Work order {p['open_work_order']} is open for it; schedule it before the machine runs further."
		else:
			action = "Create a Maintenance Work Order and plan the stop as planned downtime."
		out.append(
			{
				"rule_key": rule_key(p["name"], p.get("since"), status),
				"category": "Maintenance",
				"severity": SEVERITY[status],
				"title": f"{title} on {p['machine']} is {status.lower()}",
				"suggestion": (
					f"{p['machine']} has used {used:,.1f} of {interval:,.1f} {unit} "
					f"({p.get('percent', 0):.0f} percent) since its last service on {p.get('since')}.{when} {action}"
				),
				"reference_doctype": "Maintenance Plan",
				"reference_name": p["name"],
				"evidence": {
					"machine": p["machine"],
					"trigger": p.get("trigger"),
					"interval": interval,
					"used": used,
					"percent": p.get("percent"),
					"since": str(p.get("since")),
					"due_on": str(p["due_on"]) if p.get("due_on") else None,
					"open_work_order": p.get("open_work_order"),
				},
			}
		)
	return out
