# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A machine that reports events. Its state, last-seen time and current job are kept here.

The current job is an External Reference of type Job Card, so the core never links to an ERP
DocType. Whenever it changes, every dotted path registered under the `foames_machine_job_changed`
hook is called with the machine, the previous reference (or None) and the time of the change; an
ERP adapter uses that to roll the counts of the job that ended up to its ERP.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

REFERENCE_TYPES = {
	"workstation_reference": "Workstation",
	"location_reference": "Location",
	"current_job_reference": "Job Card",
}


class Machine(Document):
	def _set_defaults(self):
		# Frappe fills an empty Time field with the current time when a document is created. An
		# empty Shift Start means the whole day is scheduled (see oee_period.scheduled_window), so a
		# machine created without one must stay without one.
		shift_start = self.shift_start
		super()._set_defaults()
		if not shift_start:
			self.shift_start = None

	def validate(self):
		if not self.title:
			self.title = self.code
		if not self.source_id:
			self.source_id = self.code
		for field, expected in REFERENCE_TYPES.items():
			if self.get(field):
				actual = frappe.db.get_value("External Reference", self.get(field), "reference_type")
				if actual != expected:
					frappe.throw(
						_("{0} must point to a {1} record, not {2}").format(
							self.meta.get_label(field), expected, actual
						)
					)
		if self.job_changed():
			self.current_job_since = (
				(self.flags.job_changed_at or now_datetime()) if self.current_job_reference else None
			)
		elif not self.current_job_reference:
			self.current_job_since = None

	def on_update(self):
		if self.job_changed():
			previous = (self.get_doc_before_save() or frappe._dict()).get("current_job_reference")
			at = self.current_job_since or self.flags.job_changed_at or now_datetime()
			for handler in frappe.get_hooks("foames_machine_job_changed") or []:
				frappe.get_attr(handler)(self, previous, get_datetime(at))

	def job_changed(self) -> bool:
		if self.is_new():
			return bool(self.current_job_reference)
		before = self.get_doc_before_save()
		if before is None:
			return self.has_value_changed("current_job_reference")
		return (before.current_job_reference or None) != (self.current_job_reference or None)

	def set_current_job(self, reference: str | None, at=None):
		"""Start a job on this machine (or end the current one with None). Counts and run time
		from `at` on belong to the new job; those before it to the previous one."""
		if (reference or None) == (self.current_job_reference or None):
			return
		self.flags.job_changed_at = get_datetime(at) if at else now_datetime()
		self.current_job_reference = reference or None
		self.save()

	def set_state(self, state: str, at):
		"""Record a state change and open or close downtime around it."""
		previous = self.status
		self.status = state
		self.last_seen = at
		self.db_update()
		if state == previous:
			return
		from foames.foames_mes.doctype.downtime_record.downtime_record import (
			close_open_downtime,
			open_downtime,
		)

		if state == "Down":
			open_downtime(self.name, at)
		elif previous == "Down":
			close_open_downtime(self.name, at)


def get_machine_by_source(source_id: str) -> str | None:
	return frappe.db.get_value(
		"Machine", {"source_id": source_id, "disabled": 0}, "name"
	) or frappe.db.get_value("Machine", {"name": source_id, "disabled": 0}, "name")
