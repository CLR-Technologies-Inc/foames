# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_to_date, now_datetime


def mark_stale_machines_unknown():
	"""A machine that has not reported for the configured time is Unknown, not quietly Running."""
	minutes = frappe.db.get_single_value("Machine Data Settings", "stale_after_minutes") or 15
	cutoff = add_to_date(now_datetime(), minutes=-minutes)
	stale = frappe.get_all(
		"Machine",
		{"status": ("not in", ("Unknown", "Down")), "last_seen": ("<", cutoff), "disabled": 0},
		pluck="name",
	)
	for name in stale:
		frappe.get_doc("Machine", name).set_state("Unknown", now_datetime())
	return stale


def run_suggestion_rules():
	"""Scheduled hourly: raise suggestions from the built-in and registered rules."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
	from foames.foames_mes.floor import collect_findings, floor_snapshot

	return raise_suggestions(collect_findings(floor_snapshot(days=1)))


def compute_daily_oee():
	from foames.foames_mes.doctype.oee_period.oee_period import compute_daily_oee as compute

	return compute()
