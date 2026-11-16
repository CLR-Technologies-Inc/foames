# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_mes.material import kanban_cards


class LinesideBin(Document):
	def validate(self):
		for field in (
			"reorder_qty",
			"max_qty",
			"container_qty",
			"replenishment_lead_minutes",
			"quantity_per_unit",
		):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(self.meta.get_label(field)))
		if self.max_qty and self.reorder_qty and self.max_qty < self.reorder_qty:
			frappe.throw(_("The maximum must be at least the reorder point"))
		if self.replenishment_method == "Kanban" and not self.container_qty:
			frappe.throw(_("A kanban loop needs a container quantity"))
		self.mpc_level = (
			frappe.db.get_value("Material Handling Profile", self.material_profile, "mpc_level")
			if self.material_profile
			else 1
		) or 1
		if self.stock_source == "Manual" and self.has_value_changed("read_qty"):
			# A person counted the bin: the count replaces the estimate, and a count above the estimate
			# means material arrived, which starts a new replenishment cycle.
			now = now_datetime()
			if self.is_new() or (self.read_qty or 0) > (self.on_hand or 0):
				self.last_replenished_at = now
			self.last_read_at = now
			self.consumed_since_read = 0
			self.on_hand = self.read_qty or 0
		if self.replenishment_method == "Kanban" and self.container_qty and self.per_hour:
			self.recommended_kanban_cards = kanban_cards(
				self.per_hour,
				(self.replenishment_lead_minutes or 0) / 60.0,
				self.container_qty,
				safety_percent=self.warn_margin_percent or 0,
			)
