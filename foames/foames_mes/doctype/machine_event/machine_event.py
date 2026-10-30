# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""An event reported by a machine, and what FoaMES does with it.

Processing happens after insert: a State event moves the machine's state and opens or closes
downtime; a Count event becomes a delta against the previous reading of the same counter; an Alarm
marks the machine Down. Every other event only refreshes the machine's last-seen time.

Other apps extend the processing through the `foames_machine_event_handlers` hook: each dotted
path is called with the processed event and its machine, after the steps above.
"""

import frappe
from frappe.model.document import Document

from foames.foames_mes.counters import counter_delta


class MachineEvent(Document):
	def validate(self):
		if self.event_type == "Count" and self.counter_name:
			self.counter_name = self.counter_name.lower()

	def after_insert(self):
		try:
			self.process()
		except Exception:
			# Keep the raw event; a bad event must never drop the ones after it.
			frappe.log_error(title=f"Machine Event {self.name}", message=frappe.get_traceback())
			self.db_set("processing_note", frappe.get_traceback()[-500:])

	def process(self):
		machine = frappe.get_doc("Machine", self.machine)
		if self.event_type == "State":
			machine.set_state(self.state, self.timestamp)
		elif self.event_type == "Count":
			previous = frappe.db.get_value(
				"Machine Event",
				{
					"machine": self.machine,
					"event_type": "Count",
					"counter_name": self.counter_name,
					"name": ("!=", self.name),
					"timestamp": ("<=", self.timestamp),
				},
				"counter_value",
				order_by="timestamp desc, creation desc",
			)
			self.delta = counter_delta(previous, self.counter_value, machine.counter_rollover)
			self.db_set("delta", self.delta, update_modified=False)
			machine.last_seen = self.timestamp
			machine.db_update()
		elif self.event_type == "Alarm":
			machine.set_state("Down", self.timestamp)
		else:
			machine.last_seen = self.timestamp
			machine.db_update()
		for handler in frappe.get_hooks("foames_machine_event_handlers") or []:
			frappe.get_attr(handler)(self, machine)
		self.db_set("processed", 1, update_modified=False)
