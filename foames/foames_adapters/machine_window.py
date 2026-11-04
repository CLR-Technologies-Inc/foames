# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""What a machine did in a window, read from its Machine Events: the counter totals, the state it
carried in and the state changes inside. Shared by the adapters that roll machine data up to an
ERP job (ERPNext Job Cards, S/4HANA order operations); the arithmetic on top of it is in
`erpnext/production.py` and `s4hana/production.py`.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import get_datetime


def counter_totals(machine: str, start, end) -> dict[str, float]:
	"""Sum of each counter's deltas in (start, end]."""
	# Query builder rather than a "sum(...)" string: Frappe v16 refuses SQL functions as strings.
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.counter_name, Sum(event.delta).as_("total"))
		.where(
			(event.machine == machine)
			& (event.event_type == "Count")
			& (event.timestamp > start)
			& (event.timestamp <= end)
		)
		.groupby(event.counter_name)
		.run(as_dict=True)
	)
	return {r.counter_name: r.total or 0 for r in rows}


def state_before(machine: str, at) -> str | None:
	row = frappe.get_all(
		"Machine Event",
		filters={"machine": machine, "event_type": ("in", ("State", "Alarm")), "timestamp": ("<=", at)},
		fields=["state", "event_type"],
		order_by="timestamp desc, creation desc",
		limit_page_length=1,
	)
	if not row:
		return None
	return "Down" if row[0].event_type == "Alarm" else row[0].state


def state_events(machine: str, start, end) -> list[tuple]:
	rows = frappe.get_all(
		"Machine Event",
		filters=[
			["machine", "=", machine],
			["event_type", "in", ("State", "Alarm")],
			["timestamp", ">", start],
			["timestamp", "<", end],
		],
		fields=["timestamp", "state", "event_type"],
		order_by="timestamp asc, creation asc",
	)
	return [(get_datetime(r.timestamp), "Down" if r.event_type == "Alarm" else r.state) for r in rows]
