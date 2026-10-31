# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Queries over Machine Events shared by the OEE period, the floor and the ERPNext roll-up."""

import frappe
from frappe.query_builder.functions import Sum


def counter_totals(
	machine: str, start=None, end=None, *, start_inclusive: bool = True, end_inclusive: bool = False
) -> dict[str, float]:
	"""Counter deltas per counter name for one machine, for example {"good": 120, "scrap": 3}.

	`start` and `end` bound the event timestamps; either may be None. Built with the query builder
	because Frappe v16 no longer accepts SQL functions as strings in `get_all` fields.
	"""
	ev = frappe.qb.DocType("Machine Event")
	query = (
		frappe.qb.from_(ev)
		.select(ev.counter_name, Sum(ev.delta).as_("total"))
		.where((ev.machine == machine) & (ev.event_type == "Count"))
		.groupby(ev.counter_name)
	)
	if start is not None:
		query = query.where(ev.timestamp >= start if start_inclusive else ev.timestamp > start)
	if end is not None:
		query = query.where(ev.timestamp <= end if end_inclusive else ev.timestamp < end)
	return {r.counter_name: r.total or 0 for r in query.run(as_dict=True)}
