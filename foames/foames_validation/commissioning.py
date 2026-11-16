# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Qualification picks up where commissioning ends.

Registered on `foames_commissioning_handed_over`: when a Commissioning Package is handed over, each
machine in its scope gets a draft execution of its approved Installation Qualification (IQ)
protocol, linked to the package, so the IQ can reference the handover dossier. A machine with no
approved IQ protocol gets an Agent Suggestion to write one; FoaMES does not write protocols itself.
The first execution opened is written back to the package's Qualification Record.
"""

import frappe
from frappe import _

AGENT = "foames-validation"


def iq_protocol(machine: str) -> str | None:
	"""The machine's most recently approved IQ protocol."""
	names = frappe.get_all(
		"Validation Protocol",
		filters={"docstatus": 1, "protocol_type": "IQ", "machine": machine},
		order_by="approved_on desc, creation desc",
		pluck="name",
		limit=1,
	)
	return names[0] if names else None


def open_iq(machine: str, package: str) -> str | None:
	"""A draft IQ execution for the machine, linked to the package: an existing draft of its
	protocol is reused. None when the machine has no approved IQ protocol."""
	protocol = iq_protocol(machine)
	if not protocol:
		return None
	draft = frappe.db.get_value("Validation Execution", {"protocol": protocol, "docstatus": 0}, "name")
	if draft:
		if not frappe.db.get_value("Validation Execution", draft, "commissioning_package"):
			frappe.db.set_value("Validation Execution", draft, "commissioning_package", package)
		return draft
	execution = frappe.get_doc(
		{"doctype": "Validation Execution", "protocol": protocol, "commissioning_package": package}
	)
	execution.insert(ignore_permissions=True)
	return execution.name


def missing_protocol_finding(machine: str, package) -> dict:
	return {
		"rule_key": f"validation:iq-after-handover:{machine}",
		"category": "Quality",
		"severity": "Warning",
		"title": _("Write and approve an IQ protocol for {0}").format(machine),
		"suggestion": _(
			"Machine {0} was handed over in commissioning package {1}, but it has no approved "
			"Installation Qualification protocol. Write one, approve it, and execute it against the "
			"package's handover dossier before relying on the machine for qualified work."
		).format(machine, package.name),
		"reference_doctype": "Commissioning Package",
		"reference_name": package.name,
		"evidence": {
			"machine": machine,
			"package": package.name,
			"handed_over_on": str(package.handed_over_on),
		},
	}


def on_handover(package) -> dict:
	"""Open the IQ of every machine in the handed-over package. Returns {"executions": [...],
	"suggestions": [...]}."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	machines = list(dict.fromkeys(row.machine for row in package.items if row.machine))
	executions, findings = [], []
	for machine in machines:
		name = open_iq(machine, package.name)
		if name:
			executions.append(name)
		else:
			findings.append(missing_protocol_finding(machine, package))
	if executions and not package.qualification_name:
		package.db_set(
			{"qualification_doctype": "Validation Execution", "qualification_name": executions[0]},
			update_modified=False,
		)
	suggestions = raise_suggestions(findings, agent=AGENT) if findings else []
	return {"executions": executions, "suggestions": suggestions}
