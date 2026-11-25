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
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes.material import MPC_LABELS, readiness

OVERRIDE_ROLES = ("FoaMES Quality", "FoaMES Engineer", "System Manager")


class MaterialQueueEntry(Document):
	def validate(self):
		if (self.quantity or 0) < 0:
			frappe.throw(_("Quantity cannot be negative"))
		if (self.min_wait_minutes or 0) < 0 or (self.max_wait_minutes or 0) < 0:
			frappe.throw(_("Waits cannot be negative"))
		if self.max_wait_minutes and self.min_wait_minutes and self.max_wait_minutes < self.min_wait_minutes:
			frappe.throw(_("The maximum wait must be at least the minimum wait"))
		self.mpc_level = (
			frappe.db.get_value("Material Handling Profile", self.material_profile, "mpc_level")
			if self.material_profile
			else 1
		) or 1
		if self.status == "On Hold" and not self.hold_reason:
			frappe.throw(_("Give a hold reason"))
		now = now_datetime()
		before = self.get_doc_before_save()
		previous = before.status if before else None
		if self.status == "In Process" and previous != "In Process":
			self.check_may_start(now, previous)
			self.started_at = self.started_at or now
		if self.status in ("Done", "Withdrawn") and previous not in ("Done", "Withdrawn"):
			self.finished_at = self.finished_at or now
		self.update_readiness(now)

	def check_may_start(self, now, previous):
		state = readiness({**self.as_dict(), "status": previous or "Waiting"}, now)["state"]
		if state == "Conditioning":
			frappe.throw(
				_("This material is still in its minimum wait until {0}").format(self.ready_at_value())
			)
		if state in ("Q-time Exceeded", "Expired"):
			if not self.override_reason:
				frappe.throw(
					_("This material is {0}. Give a reason to start it anyway.").format(state.lower())
				)
			if not set(OVERRIDE_ROLES) & set(frappe.get_roles()):
				frappe.throw(
					_("Only FoaMES Quality or FoaMES Engineer can start material that is {0}").format(
						state.lower()
					)
				)
		level = int(self.mpc_level or 1)
		if level >= 5 and not self.expert_review:
			frappe.throw(
				_("MPC {0} material ({1}): record the expert review before starting").format(
					level, MPC_LABELS[level]
				)
			)
		if level == 4 and not self.expert_review:
			frappe.msgprint(
				_("MPC 4 material: a review by a human expert is recommended before starting"), alert=True
			)

	def ready_at_value(self):
		return self.ready_at or get_datetime(self.arrived_at)

	def update_readiness(self, now):
		r = readiness(self.as_dict(), now)
		self.readiness = r["state"] if self.status in ("Waiting", "In Process", "On Hold") else None
		self.ready_at = r["ready_at"]
		self.limit_at = r["limit_at"]

	def on_update(self):
		if self.has_value_changed("status") and self.status in ("In Process", "Done", "Withdrawn"):
			frappe.db.set_value(
				"Material Queue",
				self.queue,
				"last_activity",
				self.finished_at or self.started_at or now_datetime(),
				update_modified=False,
			)
