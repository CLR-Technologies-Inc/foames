# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Scheduler entry point: suggestions for NPI gates that are due or overdue with work open, for
Conditional Go conditions past their due date, and for phase review actions past due."""

import frappe
from frappe.utils import getdate, nowdate

from foames.foames_life_sciences import npi, phase_review
from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions


def check_npi_gates(today=None):
	today = getdate(today or nowdate())
	findings = []
	for name in frappe.get_all(
		"NPI Program", filters={"status": ("in", ("Active", "On Hold"))}, pluck="name"
	):
		doc = frappe.get_doc("NPI Program", name)
		gates = [
			{
				"stage": g.stage,
				"target_date": getdate(g.target_date) if g.target_date else None,
				"decision": g.decision,
				"conditions": g.conditions,
				"conditions_due": getdate(g.conditions_due) if g.conditions_due else None,
				"conditions_closed": g.conditions_closed,
			}
			for g in doc.gates
		]
		program = {
			"name": doc.name,
			"title": doc.title,
			"status": doc.status,
			"current_stage": doc.current_stage,
		}
		for finding in npi.gate_findings(program, gates, doc.deliverable_rows(), today):
			finding.update({"reference_doctype": "NPI Program", "reference_name": doc.name})
			findings.append(finding)
	for review in frappe.get_all(
		"Phase Review", filters={"docstatus": 1}, fields=["name", "stage", "npi_program"]
	):
		actions = frappe.get_all(
			"Phase Review Action",
			filters={"parent": review.name, "parenttype": "Phase Review", "status": "Open"},
			fields=["idx", "action", "owner_user", "due_date", "status"],
		)
		for a in actions:
			a["due_date"] = getdate(a["due_date"]) if a.get("due_date") else None
		for finding in phase_review.action_findings(review, actions, today):
			finding.update({"reference_doctype": "Phase Review", "reference_name": review.name})
			findings.append(finding)
	return raise_suggestions(findings, agent="foames-npi")
