# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Andon calls as pure logic: response times and the escalation rule. No Frappe dependency.

An andon call is a person on the floor asking for help at a machine: maintenance, material,
quality, a supervisor, safety. Each call type has two targets, acknowledge within N minutes and
resolve within M minutes. A call that misses a target becomes an Agent Suggestion for the people
who can act on it, once per call and target. FoaMES never stops or starts a machine because of a
call; the call records the request and how quickly it was answered.
"""

from __future__ import annotations

from datetime import datetime

OPEN_STATUSES = ("Open", "Acknowledged")
FINAL_STATUSES = ("Resolved", "Cancelled")

DEFAULT_CALL_TYPES = (
	{"code": "Maintenance", "acknowledge_within_minutes": 5, "resolve_within_minutes": 60},
	{"code": "Material", "acknowledge_within_minutes": 5, "resolve_within_minutes": 20},
	{"code": "Quality", "acknowledge_within_minutes": 10, "resolve_within_minutes": 60},
	{"code": "Supervisor", "acknowledge_within_minutes": 5, "resolve_within_minutes": 30},
	{
		"code": "Safety",
		"acknowledge_within_minutes": 2,
		"resolve_within_minutes": 30,
		"escalation_severity": "Critical",
	},
)


def minutes_between(start: datetime | None, end: datetime | None) -> float | None:
	if not start or not end:
		return None
	return max(0.0, (end - start).total_seconds() / 60.0)


def allowed_transition(previous: str | None, new: str) -> bool:
	"""Open -> Acknowledged -> Resolved, Open -> Resolved, and Cancelled from any open status. A
	resolved or cancelled call stays as it is."""
	if previous is None or previous == new:
		return True
	if previous in FINAL_STATUSES:
		return False
	if previous == "Acknowledged" and new == "Open":
		return False
	return new in ("Acknowledged", "Resolved", "Cancelled")


def overdue_andon_calls(snapshot: dict) -> list[dict]:
	"""Suggestions for open calls past their acknowledge or resolve target.

	Reads `snapshot["andon_calls"]`: dicts with name, machine, call_type, status, minutes_open,
	acknowledge_within_minutes, resolve_within_minutes, escalation_severity and the flags
	ack_escalated / resolve_escalated that mark a target already escalated.
	"""
	out = []
	for call in snapshot.get("andon_calls", []):
		if call.get("status") not in OPEN_STATUSES:
			continue
		minutes = call.get("minutes_open") or 0
		severity = call.get("escalation_severity") or "Warning"
		ack_within = call.get("acknowledge_within_minutes") or 0
		resolve_within = call.get("resolve_within_minutes") or 0
		where = f"{call['machine']}"
		evidence = {
			"andon_call": call["name"],
			"call_type": call.get("call_type"),
			"status": call.get("status"),
			"minutes_open": round(minutes, 1),
			"raised_by": call.get("raised_by"),
			"note": call.get("note"),
		}
		if (
			call.get("status") == "Open"
			and ack_within > 0
			and minutes >= ack_within
			and not call.get("ack_escalated")
		):
			out.append(
				{
					"rule_key": f"andon:{call['name']}:acknowledge",
					"category": "Andon",
					"severity": severity,
					"title": f"{call.get('call_type')} call at {where} unanswered for {minutes:.0f} min",
					"suggestion": f"Andon call {call['name']} ({call.get('call_type')}) at {where} has had no answer for {minutes:.0f} minutes; the target is {ack_within} minutes. Send someone and acknowledge the call, or cancel it if it is no longer needed.",
					"reference_doctype": "Andon Call",
					"reference_name": call["name"],
					"evidence": {**evidence, "acknowledge_within_minutes": ack_within},
				}
			)
		if resolve_within > 0 and minutes >= resolve_within and not call.get("resolve_escalated"):
			out.append(
				{
					"rule_key": f"andon:{call['name']}:resolve",
					"category": "Andon",
					"severity": severity,
					"title": f"{call.get('call_type')} call at {where} open for {minutes:.0f} min",
					"suggestion": f"Andon call {call['name']} ({call.get('call_type')}) at {where} is still {call.get('status').lower()} after {minutes:.0f} minutes; the target to resolve it is {resolve_within} minutes. Escalate to the next level of support or record what is blocking it.",
					"reference_doctype": "Andon Call",
					"reference_name": call["name"],
					"evidence": {**evidence, "resolve_within_minutes": resolve_within},
				}
			)
	return out
