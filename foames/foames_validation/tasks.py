# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe


def check_requalification(today=None) -> list[str]:
	"""Scheduled daily: raise an Agent Suggestion for each qualification that is Due Soon or Expired.
	Returns the suggestions created or reopened."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
	from foames.foames_validation.api import qualification_rows
	from foames.foames_validation.qualification import findings

	if not frappe.db.table_exists("Validation Execution"):
		return []
	return raise_suggestions(findings(qualification_rows(today=today)), agent="foames-validation")
