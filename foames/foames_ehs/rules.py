# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""EHS checks wired into the MES.

- `on_state_changed` is registered under `foames_machine_state_changed`: the moment a machine with
  an active lockout permit reports Running, a Critical Agent Suggestion is raised. FoaMES does not
  stop the machine (agents suggest; people act).
- `running_under_lockout` is registered under `foames_suggestion_rules`, so the hourly rules and any
  agent that runs them on the floor snapshot catch the same condition.
- `check_ehs` runs hourly: expires permits past their end, and raises suggestions for overdue
  corrective actions, incidents without a root cause and hazard assessments due for review.
"""

import frappe
from frappe.utils import get_datetime, getdate, now_datetime

from foames.foames_ehs import ehs

AGENT = "foames-ehs"


def _raise(findings: list[dict]) -> list[str]:
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	return raise_suggestions(findings, agent=AGENT)


def on_state_changed(machine, previous_state, state, at) -> list[str]:
	"""Registered under `foames_machine_state_changed`. A failure here is logged and never stops the
	machine event from being recorded."""
	if state != "Running":
		return []
	try:
		from foames.foames_ehs.doctype.safety_permit.safety_permit import active_permits

		machines = [{"name": machine.name, "status": state, "last_seen": at}]
		return _raise(ehs.lockout_findings(machines, active_permits([machine.name])))
	except Exception:
		frappe.log_error(title="FoaMES EHS lockout check", message=frappe.get_traceback())
		return []


def running_under_lockout(snapshot: dict) -> list[dict]:
	"""Registered under `foames_suggestion_rules`: machines on the floor snapshot that report Running
	while an active permit holds locks on them."""
	from foames.foames_ehs.doctype.safety_permit.safety_permit import active_permits

	machines = [m for m in snapshot.get("machines", []) if m.get("status") == "Running"]
	if not machines:
		return []
	return ehs.lockout_findings(machines, active_permits([m["name"] for m in machines]))


def check_ehs(now=None) -> list[str]:
	"""Scheduled hourly. Returns the suggestions created or reopened."""
	from foames.foames_ehs.doctype.safety_permit.safety_permit import active_permits

	now = get_datetime(now) if now else now_datetime()
	today = getdate(now)
	findings = []

	permits = active_permits()
	findings.extend(ehs.expired_permit_findings(permits, now))
	for permit in permits:
		if ehs.is_expired(permit, now):
			doc = frappe.get_doc("Safety Permit", permit["name"])
			doc.status = "Expired"
			doc.flags.ignore_permissions = True
			doc.save()

	open_incidents = frappe.get_all(
		"Safety Incident",
		filters={"status": ("!=", "Closed")},
		fields=["name", "incident_type", "occurred_on", "machine", "status", "root_cause", "recordable"],
		order_by="name",
	)
	for i in open_incidents:
		i["occurred_on"] = get_datetime(i["occurred_on"])
	findings.extend(ehs.investigation_findings(open_incidents, today))

	if open_incidents:
		actions = frappe.get_all(
			"EHS Action",
			filters={
				"parenttype": "Safety Incident",
				"parent": ("in", [i["name"] for i in open_incidents]),
				"status": "Open",
				"due_on": ("is", "set"),
			},
			fields=["parent", "name", "action", "action_owner", "due_on"],
			order_by="parent, idx",
		)
		for a in actions:
			a["due_on"] = getdate(a["due_on"])
		findings.extend(ehs.overdue_action_findings(actions, today))

	hazards = []
	for name in frappe.get_all(
		"Hazard Assessment", filters={"status": "Active"}, pluck="name", order_by="name"
	):
		doc = frappe.get_doc("Hazard Assessment", name)
		hazards.append(
			{
				"name": doc.name,
				"title": doc.title,
				"machine": doc.machine,
				"next_review_on": getdate(doc.next_review_on) if doc.next_review_on else None,
				"residual_level": doc.residual_level,
				"residual_score": doc.residual_score,
				"strongest_control": doc.strongest_control,
				"weaknesses": doc.weaknesses(),
			}
		)
	findings.extend(ehs.hazard_review_findings(hazards, today))
	return _raise(findings)
