# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A machine that reports events. Its state and last-seen time are kept here."""

import frappe
from frappe import _
from frappe.model.document import Document


class Machine(Document):
	def validate(self):
		if not self.title:
			self.title = self.code
		if not self.source_id:
			self.source_id = self.code
		for field, expected in (("workstation_reference", "Workstation"), ("location_reference", "Location")):
			if self.get(field):
				actual = frappe.db.get_value("External Reference", self.get(field), "reference_type")
				if actual != expected:
					frappe.throw(
						_("{0} must point to a {1} record, not {2}").format(
							self.meta.get_label(field), expected, actual
						)
					)

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
