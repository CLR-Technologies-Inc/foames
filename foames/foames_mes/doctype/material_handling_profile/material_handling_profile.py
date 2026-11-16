# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe.model.document import Document

from foames.foames_mes.material import factor_label, mpc


class MaterialHandlingProfile(Document):
	def validate(self):
		result = mpc(self.as_dict())
		self.mpc_level = result["level"]
		self.mpc_label = f"MPC {result['level']}: {result['label']}"
		self.expert_oversight = result["expert_oversight"]
		self.default_dispatch = result["default_dispatch"]
		self.safety_multiplier = result["safety_multiplier"]
		drivers = [factor_label(f) for f in result["drivers"]]
		if result["compounded"]:
			drivers.append("Three or more elevated factors (compounded one level)")
		self.mpc_drivers = "\n".join(drivers)

	def on_update(self):
		# Bins and queue entries carry the level so the floor and the rules never look it up again.
		for doctype in ("Lineside Bin", "Material Queue Entry"):
			frappe.db.set_value(
				doctype, {"material_profile": self.name}, "mpc_level", self.mpc_level, update_modified=False
			)
