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

"""Ties a data-layer signal to the physical asset it is measured at (Read) or acts on (Write).

This is what puts the data view on top of the physical one: an instrument tag such as TT-101 is
both a physical instrument and a signal, and the binding says which signal, through which
provider, in which unit. A Write binding is recorded so the view can show it; FoaMES itself never
writes to equipment."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_topology.doctype.topology_link.topology_link import check_same_tenant
from foames.foames_topology.ingest import binding_problem


class SignalBinding(Document):
	def validate(self):
		layers = dict(
			frappe.get_all(
				"Topology Asset",
				{"name": ("in", [self.signal, self.physical_asset])},
				["name", "layer"],
				as_list=True,
			)
		)
		problem = binding_problem(layers.get(self.signal), layers.get(self.physical_asset))
		if problem:
			frappe.throw(_(problem))
		self.binding_key = f"{self.signal}|{self.direction}|{self.physical_asset}"
		self.tenant = check_same_tenant(self.signal, self.physical_asset, self.tenant)
