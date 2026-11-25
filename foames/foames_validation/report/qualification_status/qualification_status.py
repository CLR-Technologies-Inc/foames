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

"""Every machine and process with an approved protocol, and where it stands: Qualified, Due Soon,
Expired, Runs Pending or Not Qualified."""

import frappe
from frappe import _
from frappe.utils import cint

from foames.foames_validation.api import qualification_rows
from foames.foames_validation.qualification import DEFAULT_DUE_SOON_DAYS


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = qualification_rows(
		machine=filters.get("machine"),
		process=filters.get("process"),
		protocol_type=filters.get("protocol_type"),
		due_soon_days=cint(filters.get("due_soon_days")) or DEFAULT_DUE_SOON_DAYS,
		for_user=True,
	)
	if filters.get("status"):
		rows = [r for r in rows if r["status"] == filters.status]
	return columns(), rows


def columns():
	return [
		{"fieldname": "subject_type", "label": _("Subject"), "fieldtype": "Data", "width": 90},
		{"fieldname": "subject", "label": _("Machine or Process"), "fieldtype": "Data", "width": 180},
		{"fieldname": "protocol_type", "label": _("Type"), "fieldtype": "Data", "width": 70},
		{"fieldname": "protocol_name", "label": _("Qualification"), "fieldtype": "Data", "width": 230},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "qualified_until", "label": _("Qualified Until"), "fieldtype": "Date", "width": 120},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 90},
		{"fieldname": "runs_passed", "label": _("Runs Passed"), "fieldtype": "Int", "width": 100},
		{"fieldname": "runs_required", "label": _("Runs Required"), "fieldtype": "Int", "width": 110},
		{
			"fieldname": "execution",
			"label": _("Latest Execution"),
			"fieldtype": "Link",
			"options": "Validation Execution",
			"width": 150,
		},
		{
			"fieldname": "protocol",
			"label": _("Protocol"),
			"fieldtype": "Link",
			"options": "Validation Protocol",
			"width": 140,
		},
	]
