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

"""An incident, near miss, unsafe condition or environmental release.

Anyone on the floor can report one. Recordability is worked out from the outcome boxes (never typed
in), so the rates and the log always agree with the record. A serious incident raises a Critical
Agent Suggestion as soon as it is saved; closing the incident needs a root cause and every action
finished or cancelled, and closes the incident's open safety suggestions.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime, today

from foames.foames_ehs.ehs import classify_incident, serious_incident_findings


class SafetyIncident(Document):
	def validate(self):
		now = now_datetime()
		if get_datetime(self.occurred_on) > now:
			frappe.throw(_("An incident cannot have happened in the future"))
		if not self.reported_on:
			self.reported_on = now
		if get_datetime(self.reported_on) < get_datetime(self.occurred_on):
			frappe.throw(_("An incident cannot be reported before it happened"))
		if not self.reported_by:
			self.reported_by = frappe.session.user
		if self.potential_severity and not 1 <= int(self.potential_severity) <= 5:
			frappe.throw(_("Potential severity runs from 1 to 5"))
		if (self.days_away or 0) < 0 or (self.days_restricted or 0) < 0:
			frappe.throw(_("Day counts cannot be negative"))
		if self.reportable_release and not self.substance:
			frappe.throw(_("Name the substance of a reportable release"))
		self.classify()
		self.validate_actions()
		self.validate_status()

	def classify(self):
		result = classify_incident(self.as_dict())
		self.recordable = int(result["recordable"])
		self.osha_outcome = result["outcome"]
		self.log_days_away = result["days_away"]
		self.log_days_restricted = result["days_restricted"]

	def validate_actions(self):
		for action in self.actions:
			if action.status == "Done" and not action.completed_on:
				action.completed_on = today()
			if action.status != "Done":
				action.completed_on = None
			if action.completed_on and getdate(action.completed_on) > getdate(today()):
				frappe.throw(_("Row {0}: an action cannot be completed in the future").format(action.idx))

	def validate_status(self):
		before = self.get_doc_before_save()
		if self.status == "Closed":
			if not (self.root_cause or "").strip():
				frappe.throw(_("Record the root cause before closing the incident"))
			open_actions = [a.idx for a in self.actions if a.status == "Open"]
			if open_actions:
				frappe.throw(
					_("Finish or cancel actions in rows {0} before closing the incident").format(
						", ".join(str(i) for i in open_actions)
					)
				)
			if not (before and before.status == "Closed"):
				self.closed_on = now_datetime()
				self.closed_by = frappe.session.user
		else:
			self.closed_on = None
			self.closed_by = None
			if self.status == "Reported" and any(a.status == "Open" for a in self.actions):
				self.status = "Actions Open"

	def on_update(self):
		from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

		if self.status == "Closed":
			close_suggestions(self.name, _("Incident {0} closed").format(self.name))
		else:
			raise_suggestions(serious_incident_findings(self.as_dict()), agent="foames-ehs")


def close_suggestions(incident: str, resolution: str):
	for name in frappe.get_all(
		"Agent Suggestion",
		filters={
			"reference_doctype": "Safety Incident",
			"reference_name": incident,
			"status": "Open",
			"category": "Safety",
		},
		pluck="name",
	):
		suggestion = frappe.get_doc("Agent Suggestion", name)
		suggestion.status = "Done"
		suggestion.resolution = resolution
		suggestion.save(ignore_permissions=True)


@frappe.whitelist()
def report_near_miss(
	title: str,
	description: str,
	machine: str | None = None,
	location: str | None = None,
	potential_severity: int | None = None,
	occurred_on: str | None = None,
) -> str:
	"""Report a near miss in one call, from a tablet on the floor, an andon station or an agent.
	The caller needs permission to create Safety Incidents (operators have it)."""
	doc = frappe.get_doc(
		{
			"doctype": "Safety Incident",
			"incident_type": "Near Miss",
			"title": title,
			"description": description,
			"machine": machine,
			"location": location,
			"potential_severity": potential_severity,
			"occurred_on": occurred_on or now_datetime(),
		}
	)
	doc.insert()
	return doc.name
