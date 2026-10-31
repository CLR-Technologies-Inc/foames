# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

from foames.foames_mes.counters import minutes_between


class DowntimeRecord(Document):
	def validate(self):
		if self.end_time:
			start, end = get_datetime(self.start_time), get_datetime(self.end_time)
			if end < start:
				frappe.throw(_("Downtime cannot end before it starts"))
			self.duration_minutes = minutes_between(start, end)
			self.status = "Closed"
		else:
			self.status = "Open"
			self.duration_minutes = None

	def close(self, at):
		# Called while a machine event is processed, possibly by the signed webhook (Guest): the
		# machine state has already moved, so the downtime closes with the same authority.
		self.end_time = at
		self.save(ignore_permissions=True)


def open_downtime(machine: str, at) -> str:
	existing = frappe.db.get_value("Downtime Record", {"machine": machine, "status": "Open"}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Downtime Record",
			"machine": machine,
			"start_time": at,
			"source": "Automatic",
		}
	).insert(ignore_permissions=True)
	return doc.name


def close_open_downtime(machine: str, at):
	for name in frappe.get_all("Downtime Record", {"machine": machine, "status": "Open"}, pluck="name"):
		frappe.get_doc("Downtime Record", name).close(at)
