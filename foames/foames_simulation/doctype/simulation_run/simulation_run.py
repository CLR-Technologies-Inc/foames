# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_simulation.simulation import (
	RUN_STATES,
	TransitionError,
	epoch_to_datetime,
	is_terminal,
	transition,
)


class SimulationRun(Document):
	def validate(self):
		if self.status not in RUN_STATES:
			frappe.throw(_("Unknown simulation status {0}").format(self.status))
		# Local transitions follow the provider's state machine; the provider is
		# still the authority — sync copies its status onto the record.
		if self.is_new():
			return
		previous = self.get_doc_before_save()
		if previous and previous.status != self.status:
			try:
				transition(previous.status, self.status)
			except TransitionError as e:
				frappe.throw(str(e))

	def before_insert(self):
		self.submitted_on = self.submitted_on or frappe.utils.now_datetime()
		if not self.title:
			self.title = "{0} {1}".format(self.case or "simulation", self.run_id or "")

	@frappe.whitelist()
	def refresh(self):
		"""Pull the provider's current status onto this record."""
		from foames.foames_simulation.api import simulation_status

		frappe.only_for(("System Manager", "FoaMES Engineer", "FoaMES Supervisor", "FoaMES Quality", "FoaMES Integration"))
		run = simulation_status(self.name)
		status = run.get("status")
		if status and status != self.status:
			# Route through validate so illegal jumps are rejected here too.
			old = self.status
			try:
				transition(old, status)
			except TransitionError:
				# The provider is authoritative: accept terminal states even when the
				# local record skipped intermediate ones (e.g. draft -> succeeded).
				if not is_terminal(status):
					raise
			self.db_set({
				"status": status,
				"error": run.get("error") or "",
				"result_summary": frappe.as_json(run.get("result") or {}),
				"finished_on": epoch_to_datetime(run.get("finished_at")),
				"artifacts": "\n".join((run.get("artifacts") or [])),
			}, update_modified=False)
		return _("Status: {0}").format(self.status)
