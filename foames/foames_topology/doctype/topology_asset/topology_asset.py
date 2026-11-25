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

"""One node of the topology graph, on the physical or the data layer.

Assets are written by the built-in sync (from Machines, machine data sources, P&ID components,
OEE and External References), by collectors through foames.foames_topology.api.ingest, or by
hand. The first two set Managed; a record made by hand is never overwritten by either."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_topology import model


class TopologyAsset(Document):
	def validate(self):
		self.title = self.title or self.asset_id
		expected = model.kind_layer(self.kind)
		if expected and expected != self.layer:
			frappe.throw(
				_("A {0} is on the {1} layer, not {2}").format(_(self.kind), _(expected), _(self.layer))
			)
		self.validate_parent()

	def validate_parent(self):
		if not self.parent_asset:
			return
		if self.parent_asset == self.name or self.parent_asset == self.asset_id:
			frappe.throw(_("An asset cannot be part of itself"))
		seen = {self.asset_id}
		current = self.parent_asset
		while current:
			if current in seen:
				frappe.throw(_("Part Of would make a loop through {0}").format(current))
			seen.add(current)
			parent = frappe.db.get_value(
				"Topology Asset", current, ["parent_asset", "tenant", "layer"], as_dict=True
			)
			if parent is None:
				break
			if current == self.parent_asset:
				if parent.tenant and self.tenant and parent.tenant != self.tenant:
					frappe.throw(_("{0} belongs to tenant {1}").format(current, parent.tenant))
			current = parent.parent_asset
