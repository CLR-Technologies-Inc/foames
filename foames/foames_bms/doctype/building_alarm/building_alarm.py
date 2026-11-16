# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A building point past a limit or no longer reporting.

Active -> Acknowledged (a person is on it) -> Closed when the value returns to normal; or
Active -> Returned (back to normal, nobody acknowledged it yet) -> Closed when acknowledged. The
engine in foames.foames_bms.engine raises, escalates and returns alarms; people acknowledge them.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class BuildingAlarm(Document):
	def acknowledge(self, note: str | None = None):
		if self.status in ("Closed",):
			frappe.throw(_("Alarm {0} is already closed").format(self.name))
		if self.status == "Acknowledged":
			return
		now = now_datetime()
		self.acknowledged_by = frappe.session.user
		self.acknowledged_at = now
		if note:
			self.note = f"{self.note}\n{note}" if self.note else note
		if self.status == "Returned":
			self.status = "Closed"
			self.closed_at = now
		else:
			self.status = "Acknowledged"
		self.save(ignore_permissions=True)
		from foames.foames_bms.engine import alarm_handled

		alarm_handled(self)


@frappe.whitelist(methods=["POST"])
def acknowledge(alarm: str, note: str | None = None) -> dict:
	"""Acknowledge a building alarm: someone is on it. Needs write on Building Alarm."""
	doc = frappe.get_doc("Building Alarm", alarm)
	doc.check_permission("write")
	doc.acknowledge(note)
	return {"name": doc.name, "status": doc.status, "acknowledged_by": doc.acknowledged_by}
