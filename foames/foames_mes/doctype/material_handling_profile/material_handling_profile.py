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
