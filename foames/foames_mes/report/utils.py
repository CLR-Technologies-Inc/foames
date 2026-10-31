# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Shared pieces of the FoaMES script reports: the date window, machine and line filters, and the
report-chart shape Frappe expects."""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, nowdate

DEFAULT_DAYS = 30
MAX_SERIES = 8


def date_window(filters, days: int = DEFAULT_DAYS):
	"""(from_datetime, to_datetime) covering whole days; the last `days` days when unset."""
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -(days - 1)))
	if from_date > to_date:
		frappe.throw(_("From Date must be before To Date"))
	return get_datetime(f"{from_date} 00:00:00"), get_datetime(f"{add_days(to_date, 1)} 00:00:00")


def machines_in_scope(filters) -> dict[str, dict]:
	"""name -> {title, line} for the machines the filters select; disabled machines are included
	when named directly, otherwise left out."""
	conditions = {}
	if filters.get("machine"):
		conditions["name"] = filters.get("machine")
	else:
		conditions["disabled"] = 0
	if filters.get("line"):
		conditions["line"] = filters.get("line")
	rows = frappe.get_all("Machine", filters=conditions, fields=["name", "title", "line"], order_by="name")
	return {r.name: r for r in rows}


def chart_of(labels, datasets, chart_type="bar", **options) -> dict:
	"""A Frappe Charts configuration the report view and the dashboard both accept."""
	chart = {
		"data": {"labels": list(labels), "datasets": datasets},
		"type": chart_type,
	}
	chart.update(options)
	return chart


def summary_item(label, value, datatype="Float", indicator=None, **extra) -> dict:
	item = {"label": _(label), "value": value, "datatype": datatype}
	if indicator:
		item["indicator"] = indicator
	item.update(extra)
	return item


def machine_filter_definitions():
	return [
		{"fieldname": "machine", "label": _("Machine"), "fieldtype": "Link", "options": "Machine"},
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data"},
	]
