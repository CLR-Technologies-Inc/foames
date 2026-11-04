# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Andon calls raised in a window, grouped by call type, machine or line: how many, how many are
still open, and how quickly they were answered and resolved (median and 90th percentile), with
how many missed their call type's targets."""

from collections import defaultdict

import frappe
from frappe import _

from foames.foames_mes.kpi import percentile
from foames.foames_mes.report.utils import chart_of, date_window, machines_in_scope, summary_item

GROUPS = ("Call Type", "Machine", "Line")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start, end = date_window(filters)
	group_by = filters.get("group_by") if filters.get("group_by") in GROUPS else "Call Type"
	machines = machines_in_scope(filters)
	calls = get_calls(list(machines), start, end, filters.get("call_type"))

	groups = defaultdict(list)
	for c in calls:
		if group_by == "Machine":
			key = c.machine
		elif group_by == "Line":
			key = machines[c.machine].line or _("No Line")
		else:
			key = c.call_type
		groups[key].append(c)

	rows = [{"group": key, **summarise(group)} for key, group in groups.items()]
	rows.sort(key=lambda r: -r["calls"])
	overall = summarise(calls)
	return (
		get_columns(group_by),
		rows,
		None,
		chart_of(
			[str(r["group"]) for r in rows],
			[{"name": _("Median Response (min)"), "values": [r["median_response"] or 0 for r in rows]}],
			"bar",
		),
		[
			summary_item(_("Calls"), overall["calls"], "Int"),
			summary_item(_("Still Open"), overall["open"], "Int", "Orange" if overall["open"] else "Green"),
			summary_item(_("Median Response (min)"), overall["median_response"] or 0, "Float"),
			summary_item(_("90th Percentile Response (min)"), overall["p90_response"] or 0, "Float"),
			summary_item(
				_("Missed Acknowledge Target"),
				overall["missed_acknowledge"],
				"Int",
				"Red" if overall["missed_acknowledge"] else "Green",
			),
		],
	)


def summarise(calls) -> dict:
	# A Float column stores an unanswered call's response as 0, so only answered calls count.
	response = [c.response_minutes or 0 for c in calls if c.acknowledged_at or c.status == "Resolved"]
	resolution = [
		c.resolution_minutes for c in calls if c.status == "Resolved" and c.resolution_minutes is not None
	]
	return {
		"calls": len(calls),
		"open": sum(1 for c in calls if c.status in ("Open", "Acknowledged")),
		"resolved": sum(1 for c in calls if c.status == "Resolved"),
		"cancelled": sum(1 for c in calls if c.status == "Cancelled"),
		"median_response": percentile(response, 0.5),
		"p90_response": percentile(response, 0.9),
		"median_resolution": percentile(resolution, 0.5),
		"p90_resolution": percentile(resolution, 0.9),
		"missed_acknowledge": sum(1 for c in calls if c.ack_escalated),
		"missed_resolve": sum(1 for c in calls if c.resolve_escalated),
	}


def get_calls(machine_names, start, end, call_type=None):
	if not machine_names:
		return []
	conditions = [
		["machine", "in", machine_names],
		["raised_at", ">=", start],
		["raised_at", "<", end],
	]
	if call_type:
		conditions.append(["call_type", "=", call_type])
	return frappe.get_list(
		"Andon Call",
		filters=conditions,
		fields=[
			"name",
			"machine",
			"call_type",
			"status",
			"acknowledged_at",
			"response_minutes",
			"resolution_minutes",
			"ack_escalated",
			"resolve_escalated",
		],
	)


def get_columns(group_by):
	columns = (
		[
			{
				"fieldname": "group",
				"label": _("Machine"),
				"fieldtype": "Link",
				"options": "Machine",
				"width": 140,
			}
		]
		if group_by == "Machine"
		else [{"fieldname": "group", "label": _(group_by), "fieldtype": "Data", "width": 140}]
	)
	minutes = [
		("median_response", _("Median Response (min)")),
		("p90_response", _("P90 Response (min)")),
		("median_resolution", _("Median Resolution (min)")),
		("p90_resolution", _("P90 Resolution (min)")),
	]
	counts = [
		("calls", _("Calls")),
		("open", _("Open")),
		("resolved", _("Resolved")),
		("cancelled", _("Cancelled")),
	]
	missed = [
		("missed_acknowledge", _("Missed Acknowledge")),
		("missed_resolve", _("Missed Resolve")),
	]
	columns += [{"fieldname": f, "label": label, "fieldtype": "Int", "width": 90} for f, label in counts]
	columns += [{"fieldname": f, "label": label, "fieldtype": "Float", "width": 140} for f, label in minutes]
	columns += [{"fieldname": f, "label": label, "fieldtype": "Int", "width": 130} for f, label in missed]
	return columns
