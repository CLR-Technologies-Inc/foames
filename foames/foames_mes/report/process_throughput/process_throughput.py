# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Cases completed per day or week and their cycle times, from a saved Process Event Log.

A case completes at its last event. Cycle time is first to last event of the case, so a case with a
single event has a cycle time of zero and still counts as throughput. Without a log chosen, the
latest extracted log is used.
"""

from collections import defaultdict
from datetime import timedelta
from statistics import mean, median

import frappe
from frappe import _
from frappe.utils import getdate

from foames.foames_mes.kpi import percentile
from foames.foames_mes.report.utils import chart_of, summary_item
from foames.foames_process_mining.discovery import throughput


def execute(filters=None):
	filters = frappe._dict(filters or {})
	name = filters.get("event_log") or latest_log()
	if not name:
		return get_columns(), [], _("No extracted Process Event Log yet"), None, []
	doc = frappe.get_doc("Process Event Log", name)
	frappe.has_permission(doc.doctype, "read", doc, throw=True)
	log = doc.load()
	interval = filters.get("interval") if filters.get("interval") in ("Daily", "Weekly") else "Daily"
	activity = filters.get("completing_activity")

	buckets = defaultdict(lambda: {"cases": 0, "events": 0, "durations": []})
	for events in log.traces().values():
		if activity and not any(e.activity == activity for e in events):
			continue
		first, last = events[0].timestamp, events[-1].timestamp
		key = bucket(getdate(last), interval)
		b = buckets[key]
		b["cases"] += 1
		b["events"] += len(events)
		b["durations"].append((last - first).total_seconds() / 3600.0)

	rows = []
	for key in sorted(buckets):
		b = buckets[key]
		rows.append(
			{
				"period": key,
				"cases": b["cases"],
				"events": b["events"],
				"median_hours": median(b["durations"]),
				"mean_hours": mean(b["durations"]),
				"p90_hours": percentile(b["durations"], 0.9),
				"max_hours": max(b["durations"]),
			}
		)

	stats = throughput(log)
	return (
		get_columns(),
		rows,
		None,
		get_chart(rows),
		[
			summary_item(_("Cases"), stats["cases"], "Int"),
			summary_item(_("Cases per Day"), stats["cases_per_day"] or 0, "Float"),
			summary_item(_("Median Cycle Time (h)"), (stats["median_seconds"] or 0) / 3600.0, "Float"),
			summary_item(_("Event Log"), doc.title or doc.name, "Data"),
		],
	)


def latest_log():
	return frappe.db.get_value(
		"Process Event Log", {"status": "Extracted"}, "name", order_by="extracted_on desc"
	)


def bucket(day, interval):
	if interval == "Weekly":
		return day - timedelta(days=day.weekday())
	return day


def get_columns():
	return [
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Date", "width": 110},
		{"fieldname": "cases", "label": _("Cases Completed"), "fieldtype": "Int", "width": 120},
		{"fieldname": "events", "label": _("Events"), "fieldtype": "Int", "width": 80},
		{"fieldname": "median_hours", "label": _("Median Cycle (h)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "mean_hours", "label": _("Mean Cycle (h)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "p90_hours", "label": _("P90 Cycle (h)"), "fieldtype": "Float", "width": 110},
		{"fieldname": "max_hours", "label": _("Longest Cycle (h)"), "fieldtype": "Float", "width": 120},
	]


def get_chart(rows):
	return chart_of(
		[str(r["period"]) for r in rows],
		[
			{"name": _("Cases"), "chartType": "bar", "values": [r["cases"] for r in rows]},
			{
				"name": _("Median Cycle (h)"),
				"chartType": "line",
				"values": [round(r["median_hours"], 2) for r in rows],
			},
		],
		"axis-mixed",
		colors=["#2490ef", "#ffa00a"],
		lineOptions={"regionFill": 0},
	)
