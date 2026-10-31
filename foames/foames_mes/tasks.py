# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_to_date, now_datetime


def mark_stale_machines_unknown():
	"""A machine that has not reported for the configured time is Unknown, not quietly Running.

	The transition is written as a Machine Event (source System) at the moment the signal counted as
	lost, so the OEE ledger, which is built from state events, stops crediting run time there.
	"""
	minutes = frappe.db.get_single_value("Machine Data Settings", "stale_after_minutes") or 15
	cutoff = add_to_date(now_datetime(), minutes=-minutes)
	# Plain SQL through the query builder: a machine with no Last Seen at all does not match "<"
	# (there is nothing to time out), and the value comes back exactly as stored. On Frappe v15,
	# get_all returned this Datetime column empty for a row its own filter had matched, which
	# would have stamped the event "now" instead of at last_seen + minutes.
	machine = frappe.qb.DocType("Machine")
	stale = (
		frappe.qb.from_(machine)
		.select(machine.name, machine.last_seen)
		.where(
			machine.status.notin(["Unknown", "Down"]) & (machine.last_seen < cutoff) & (machine.disabled == 0)
		)
		.run(as_dict=True)
	)
	for m in stale:
		frappe.get_doc(
			{
				"doctype": "Machine Event",
				"machine": m.name,
				"event_type": "State",
				"state": "Unknown",
				"source": "System",
				"timestamp": add_to_date(m.last_seen, minutes=minutes),
				"text": f"no event for {minutes} minutes",
			}
		).insert(ignore_permissions=True)
	return [m.name for m in stale]


def run_suggestion_rules():
	"""Scheduled hourly: raise suggestions from the built-in and registered rules."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
	from foames.foames_mes.floor import collect_findings, floor_snapshot

	return raise_suggestions(collect_findings(floor_snapshot(days=1)))


def compute_daily_oee():
	from foames.foames_mes.doctype.oee_period.oee_period import compute_daily_oee as compute

	return compute()
