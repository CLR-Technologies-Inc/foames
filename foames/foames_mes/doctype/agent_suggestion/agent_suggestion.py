# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A suggestion raised by the built-in rules or by an external agent, for a person to act on."""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AgentSuggestion(Document):
	def validate(self):
		if self.status in ("Accepted", "Dismissed", "Done") and not self.resolved_on:
			self.resolved_on = now_datetime()
			self.resolved_by = frappe.session.user
		if self.status == "Open":
			self.resolved_on = None
			self.resolved_by = None
		if not self.rule_key:
			self.rule_key = f"{self.agent or 'manual'}:{self.name or frappe.generate_hash(length=10)}"


def raise_suggestions(findings: list[dict], agent: str = "foames-rules") -> list[str]:
	"""Insert findings whose rule_key is not already open. A finding whose key belongs to a resolved
	suggestion reopens that suggestion with the new evidence. Returns the names created or reopened."""
	created = []
	for finding in findings:
		existing = frappe.db.get_value(
			"Agent Suggestion", {"rule_key": finding["rule_key"]}, ["name", "status"]
		)
		if existing and existing[1] == "Open":
			continue
		if existing:
			doc = frappe.get_doc("Agent Suggestion", existing[0])
			doc.update({**finding, "agent": agent, "status": "Open", "resolution": None})
		else:
			doc = frappe.get_doc({"doctype": "Agent Suggestion", "agent": agent, **finding})
		if isinstance(doc.evidence, dict | list):
			doc.evidence = frappe.as_json(doc.evidence)
		doc.save(ignore_permissions=True)
		created.append(doc.name)
	return created
