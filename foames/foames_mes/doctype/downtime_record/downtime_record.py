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
