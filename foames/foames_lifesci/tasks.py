# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Scheduler entry point: suggestions for NPI gates that are due or overdue with work open, and for
Conditional Go conditions past their due date."""

import frappe
from frappe.utils import getdate, nowdate

from foames.foames_lifesci import npi
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
	return raise_suggestions(findings, agent="foames-npi")
