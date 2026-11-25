# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Incidents by month and type, with the recordable, DART and lost-time rates for the period.

Rates are per 200,000 hours worked; FoaMES does not know payroll hours, so they appear when the
Hours Worked filter is filled in. The near-miss ratio (leading events per recordable case) needs no
hours. Recordability is the stored classification, worked out from each incident's outcome boxes.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from foames.foames_ehs.ehs import INCIDENT_TYPES, incident_rates
from foames.foames_mes.report.utils import chart_of, date_window, summary_item

FIELDS = [
	"name",
	"incident_type",
	"occurred_on",
	"work_related",
	"death",
	"days_away",
	"days_restricted",
	"medical_treatment",
	"loss_of_consciousness",
	"significant_diagnosis",
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start, end = date_window(filters, days=365)
	conditions = {"occurred_on": ("between", (start, end))}
	if filters.get("machine"):
		conditions["machine"] = filters.machine
	if filters.get("location"):
		conditions["location"] = ("like", f"%{filters.location}%")
	incidents = frappe.get_list("Safety Incident", filters=conditions, fields=FIELDS, order_by="occurred_on")
	hours = flt(filters.get("hours_worked")) or None
	rows = month_rows(incidents)
	totals = incident_rates(incidents, hours)
	chart = (
		chart_of(
			[r["month"] for r in rows],
			[{"name": _(t), "values": [r[key(t)] for r in rows]} for t in INCIDENT_TYPES],
			chart_type="bar",
			barOptions={"stacked": 1},
		)
		if rows
		else None
	)
	return get_columns(), rows, None, chart, summary(totals)


def key(incident_type: str) -> str:
	return frappe.scrub(incident_type)


def month_rows(incidents: list[dict]) -> list[dict]:
	months: dict[str, list] = {}
	for i in incidents:
		months.setdefault(getdate(i["occurred_on"]).strftime("%Y-%m"), []).append(i)
	rows = []
	for month, items in sorted(months.items()):
		r = incident_rates(items, None)
		row = {
			"month": month,
			"incidents": r["incidents"],
			"recordable": r["recordable"],
			"dart": r["dart"],
			"lost_time": r["lost_time"],
			"days_away": r["days_away"],
			"days_restricted": r["days_restricted"],
		}
		row.update({key(t): r["by_type"][t] for t in INCIDENT_TYPES})
		rows.append(row)
	return rows


def summary(t: dict) -> list[dict]:
	def rate(value):
		return round(value, 2) if value is not None else _("Enter hours worked")

	return [
		summary_item(_("Recordable Cases"), t["recordable"], "Int", "Red" if t["recordable"] else "Green"),
		summary_item(_("TRIR"), rate(t["trir"]), "Float" if t["trir"] is not None else "Data"),
		summary_item(_("DART Rate"), rate(t["dart_rate"]), "Float" if t["dart_rate"] is not None else "Data"),
		summary_item(_("Lost Time Rate"), rate(t["ltir"]), "Float" if t["ltir"] is not None else "Data"),
		summary_item(_("Days Away"), t["days_away"], "Int"),
		summary_item(_("Leading Events"), t["leading"], "Int", "Blue"),
		summary_item(
			_("Leading Events per Recordable"),
			round(t["near_miss_ratio"], 1) if t["near_miss_ratio"] is not None else "-",
			"Float" if t["near_miss_ratio"] is not None else "Data",
		),
	]


def get_columns():
	columns = [
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 90},
		{"fieldname": "incidents", "label": _("Incidents"), "fieldtype": "Int", "width": 90},
		{"fieldname": "recordable", "label": _("Recordable"), "fieldtype": "Int", "width": 100},
		{"fieldname": "dart", "label": _("DART Cases"), "fieldtype": "Int", "width": 100},
		{"fieldname": "lost_time", "label": _("Lost Time"), "fieldtype": "Int", "width": 90},
		{"fieldname": "days_away", "label": _("Days Away"), "fieldtype": "Int", "width": 90},
		{"fieldname": "days_restricted", "label": _("Days Restricted"), "fieldtype": "Int", "width": 110},
	]
	columns += [
		{"fieldname": key(t), "label": _(t), "fieldtype": "Int", "width": 110} for t in INCIDENT_TYPES
	]
	return columns
