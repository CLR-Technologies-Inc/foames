# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One service of a Maintenance Plan.

Starting the work order records the stop as a Downtime Record with the plan's reason, so the OEE
ledger sees it (as planned downtime when the reason counts as planned). Completing it closes that
record, restarts the plan's meter from the completion time and closes the plan's open maintenance
suggestions.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes.counters import minutes_between


class MaintenanceWorkOrder(Document):
	def before_insert(self):
		plan = frappe.get_doc("Maintenance Plan", self.maintenance_plan)
		meter = plan.measure()
		self.plan_status_at_raise = meter["status"]
		self.meter_at_raise = meter["used"]
		if not self.due_on:
			self.due_on = meter["due_on"]

	def validate(self):
		plan = frappe.db.get_value(
			"Maintenance Plan", self.maintenance_plan, ["machine", "title", "instructions"], as_dict=True
		)
		if not plan:
			frappe.throw(_("Maintenance Plan {0} does not exist").format(self.maintenance_plan))
		self.machine = plan.machine
		self.title = self.title or plan.title
		before = self.get_doc_before_save()
		if before and before.status == "Completed" and self.status != "Completed":
			frappe.throw(_("A completed work order cannot be reopened; raise a new one"))
		now = now_datetime()
		if self.status in ("In Progress", "Completed") and not self.started_on:
			self.started_on = now
		if self.status == "Completed":
			if not self.completed_on:
				self.completed_on = now
			if get_datetime(self.completed_on) > now:
				frappe.throw(_("A work order cannot be completed in the future"))
			if get_datetime(self.completed_on) < get_datetime(self.started_on):
				frappe.throw(_("A work order cannot be completed before it started"))
			self.completed_by = self.completed_by or frappe.session.user
			self.actual_minutes = minutes_between(
				get_datetime(self.started_on), get_datetime(self.completed_on)
			)
		else:
			self.completed_on = None
			self.completed_by = None
			self.actual_minutes = None

	def on_update(self):
		if self.status == "In Progress":
			self.record_downtime()
		elif self.status == "Completed":
			if self.downtime_record:
				self.close_downtime(self.completed_on)
			else:
				self.record_downtime(closed=True)
			self.complete_plan()
		elif self.status == "Cancelled":
			self.close_downtime(now_datetime())
		self.refresh_plan_link()

	def record_downtime(self, closed: bool = False):
		"""Open a Downtime Record for the stop with the plan's reason. A stop already open on the
		machine is reused and given the reason if it has none. A work order completed without being
		started first gets a closed record from its start to its completion, when that took time."""
		reason = frappe.db.get_value("Maintenance Plan", self.maintenance_plan, "downtime_reason")
		if not reason or self.downtime_record:
			return
		if closed and not (self.actual_minutes and self.actual_minutes > 0):
			return
		existing = (
			None
			if closed
			else frappe.db.get_value("Downtime Record", {"machine": self.machine, "status": "Open"}, "name")
		)
		if existing:
			record = frappe.get_doc("Downtime Record", existing)
			if not record.reason:
				record.reason = reason
			note = _("Maintenance {0}").format(self.name)
			record.notes = f"{record.notes}\n{note}" if record.notes else note
			record.save(ignore_permissions=True)
		else:
			record = frappe.get_doc(
				{
					"doctype": "Downtime Record",
					"machine": self.machine,
					"reason": reason,
					"source": "Manual",
					"start_time": self.started_on,
					"end_time": self.completed_on if closed else None,
					"notes": _("Maintenance {0}: {1}").format(self.name, self.title),
				}
			).insert(ignore_permissions=True)
		self.db_set("downtime_record", record.name, update_modified=False)

	def close_downtime(self, at):
		if not self.downtime_record:
			return
		record = frappe.get_doc("Downtime Record", self.downtime_record)
		if record.status == "Open":
			record.close(max(get_datetime(at), get_datetime(record.start_time)))

	def complete_plan(self):
		"""Restart the plan's meter at the completion time and close its open maintenance suggestions.
		A completion older than the plan's last service (entered late) does not move the meter back."""
		plan = frappe.get_doc("Maintenance Plan", self.maintenance_plan)
		completed = get_datetime(self.completed_on)
		if not plan.last_done_on or completed > get_datetime(plan.last_done_on):
			plan.last_done_on = completed
			plan.last_work_order = self.name
			plan.flags.ignore_permissions = True
			plan.save()
		for name in frappe.get_all(
			"Agent Suggestion",
			filters={
				"reference_doctype": "Maintenance Plan",
				"reference_name": plan.name,
				"status": "Open",
				"category": "Maintenance",
			},
			pluck="name",
		):
			suggestion = frappe.get_doc("Agent Suggestion", name)
			suggestion.status = "Done"
			suggestion.resolution = _("Serviced by {0}").format(self.name)
			suggestion.save(ignore_permissions=True)

	def refresh_plan_link(self):
		from foames.foames_mes.doctype.maintenance_plan.maintenance_plan import open_work_order

		frappe.db.set_value(
			"Maintenance Plan",
			self.maintenance_plan,
			"open_work_order",
			open_work_order(self.maintenance_plan),
			update_modified=False,
		)
