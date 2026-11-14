# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The control plan a PFMEA implies: one line per failure chain, in operation order, with the
characteristic, its special characteristic class, the specification, the prevention and detection
controls as the control and evaluation methods, the SPC measurement, the sample size and frequency,
and the reaction plan. Obsolete PFMEAs are left out unless one is chosen."""

import frappe
from frappe import _

from foames.foames_mes.report.pfmea_risk_register.pfmea_risk_register import pfmea_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = [
		r for r in pfmea_rows(filters) if not filters.get("special_only") or r.get("special_characteristic")
	]
	return get_columns(), rows


def get_columns():
	return [
		{"fieldname": "pfmea", "label": _("PFMEA"), "fieldtype": "Link", "options": "PFMEA", "width": 120},
		{"fieldname": "op_no", "label": _("Op"), "fieldtype": "Data", "width": 60},
		{"fieldname": "process_step", "label": _("Process Step"), "fieldtype": "Data", "width": 160},
		{
			"fieldname": "machine",
			"label": _("Machine"),
			"fieldtype": "Link",
			"options": "Machine",
			"width": 110,
		},
		{
			"fieldname": "function_requirement",
			"label": _("Characteristic"),
			"fieldtype": "Data",
			"width": 180,
		},
		{"fieldname": "special_characteristic", "label": _("Class"), "fieldtype": "Data", "width": 60},
		{
			"fieldname": "specification",
			"label": _("Specification / Tolerance"),
			"fieldtype": "Data",
			"width": 140,
		},
		{"fieldname": "failure_mode", "label": _("Failure Mode"), "fieldtype": "Data", "width": 160},
		{"fieldname": "prevention_controls", "label": _("Control Method"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "detection_controls",
			"label": _("Evaluation Technique"),
			"fieldtype": "Data",
			"width": 180,
		},
		{"fieldname": "measurement_name", "label": _("SPC Measurement"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "sample_size_frequency",
			"label": _("Sample / Frequency"),
			"fieldtype": "Data",
			"width": 120,
		},
		{"fieldname": "reaction_plan", "label": _("Reaction Plan"), "fieldtype": "Data", "width": 200},
		{"fieldname": "action_priority", "label": _("AP"), "fieldtype": "Data", "width": 50},
	]
