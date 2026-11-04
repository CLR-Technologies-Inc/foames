# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A Shewhart control chart of one machine measurement: I-MR over single readings, or X-bar R over
consecutive subgroups, with the Nelson or Western Electric run rules marked on each point.

The chart is drawn from Measurement-type Machine Events. Limits come from the first `baseline`
readings when that filter is set (Phase II: judge new readings against a known-good period) and
from every reading in the window otherwise (Phase I trial limits).
"""

import frappe
from frappe import _
from frappe.utils import cint

from foames.foames_mes import spc
from foames.foames_mes.report.utils import chart_of, date_window, summary_item
from foames.foames_mes.spc_monitor import chart_data

CHARTS = ("I-MR", "X-bar R")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("machine") or not filters.get("measurement"):
		return get_columns("I-MR"), [], _("Choose a machine and a measurement"), None, []
	frappe.has_permission("Machine", "read", doc=filters.machine, throw=True)
	start, end = date_window(filters, days=7)
	chart = filters.get("chart") if filters.get("chart") in CHARTS else "I-MR"
	rules = filters.get("rules") if filters.get("rules") in spc.RULE_SETS else "Nelson"
	size = cint(filters.get("subgroup_size")) or spc.DEFAULT_SUBGROUP_SIZE
	if chart == "X-bar R" and not 2 <= size <= spc.MAX_SUBGROUP_SIZE:
		frappe.throw(_("Subgroup size must be between 2 and {0}").format(spc.MAX_SUBGROUP_SIZE))
	data = chart_data(
		filters.machine,
		filters.measurement,
		start,
		end,
		chart=chart,
		subgroup_size=size,
		baseline_points=cint(filters.get("baseline_points")),
		rules=rules,
	)
	if not data["points"]:
		return get_columns(chart), [], _(data.get("message") or "No readings"), None, []
	rows = get_rows(data, chart)
	return get_columns(chart), rows, None, get_chart(data), get_summary(data, rows)


def get_rows(data, chart):
	signals = {}
	for s in data["signals"]:
		signals.setdefault(s["index"], []).append(s["rule"])
	secondary_signals = {}
	for s in data["secondary"]["signals"]:
		secondary_signals.setdefault(s["index"], []).append(s["rule"])
	# The MR chart starts at the second reading; the R chart lines up with the X-bar chart.
	offset = 1 if chart == "I-MR" else 0
	secondary = data["secondary"]["points"]
	rows = []
	for i, point in enumerate(data["points"]):
		k = i - offset
		spread = secondary[k]["value"] if 0 <= k < len(secondary) else None
		rows.append(
			{
				"sample": i + 1,
				"at": point["at"],
				"value": point["value"],
				"cl": data["cl"],
				"ucl": data["ucl"],
				"lcl": data["lcl"],
				"spread": spread,
				"spread_ucl": data["secondary"]["ucl"],
				"signals": ", ".join(signals.get(i, [])),
				"spread_signals": ", ".join(secondary_signals.get(k, [])) if k >= 0 else "",
				"in_baseline": 1 if i < data["baseline_points"] else 0,
			}
		)
	return rows


def get_columns(chart):
	value, spread = ("Value", "Moving Range") if chart == "I-MR" else ("Subgroup Mean", "Range")
	return [
		{"fieldname": "sample", "label": _("Sample"), "fieldtype": "Int", "width": 70},
		{"fieldname": "at", "label": _("At"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "value", "label": _(value), "fieldtype": "Float", "precision": 4, "width": 110},
		{"fieldname": "cl", "label": _("CL"), "fieldtype": "Float", "precision": 4, "width": 100},
		{"fieldname": "ucl", "label": _("UCL"), "fieldtype": "Float", "precision": 4, "width": 100},
		{"fieldname": "lcl", "label": _("LCL"), "fieldtype": "Float", "precision": 4, "width": 100},
		{"fieldname": "signals", "label": _("Run Rule Signals"), "fieldtype": "Data", "width": 140},
		{"fieldname": "spread", "label": _(spread), "fieldtype": "Float", "precision": 4, "width": 110},
		{
			"fieldname": "spread_ucl",
			"label": _("{0} UCL").format(_(spread)),
			"fieldtype": "Float",
			"precision": 4,
			"width": 110,
		},
		{
			"fieldname": "spread_signals",
			"label": _("{0} Signals").format(_(spread)),
			"fieldtype": "Data",
			"width": 120,
		},
		{"fieldname": "in_baseline", "label": _("In Baseline"), "fieldtype": "Check", "width": 90},
	]


def get_chart(data):
	labels = [p["at"] for p in data["points"]]
	n = len(labels)
	return chart_of(
		labels,
		[
			{"name": _("Value"), "values": [round(p["value"], 6) for p in data["points"]]},
			{"name": _("UCL"), "values": [round(data["ucl"], 6)] * n},
			{"name": _("CL"), "values": [round(data["cl"], 6)] * n},
			{"name": _("LCL"), "values": [round(data["lcl"], 6)] * n},
		],
		"line",
		colors=["#2490ef", "#ff5858", "#29cd42", "#ff5858"],
		lineOptions={"regionFill": 0, "hideDots": 0, "dotSize": 3},
		axisOptions={"xIsSeries": 1, "shortenYAxisNumbers": 1},
	)


def get_summary(data, rows):
	flagged = sum(1 for r in rows if r["signals"])
	beyond = sum(1 for s in data["signals"] if s["rule"] in ("N1", "WE1"))
	return [
		summary_item(_("Readings"), data["readings"], "Int"),
		summary_item(_("Sigma (within)"), round(data["sigma_within"], 6), "Float"),
		summary_item(_("Points Signalled"), flagged, "Int", "Red" if flagged else "Green"),
		summary_item(_("Beyond the Limits"), beyond, "Int", "Red" if beyond else "Green"),
		summary_item(_("Baseline Points"), data["baseline_points"], "Int"),
	]
