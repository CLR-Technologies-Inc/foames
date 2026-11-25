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
from frappe.utils import cint

from foames.foames_mes.spc import MAX_SUBGROUP_SIZE


class MachineDataSettings(Document):
	def validate(self):
		from foames.foames_mes.gateway.opcua import security_config

		size = cint(self.get("spc_subgroup_size"))
		if size and not 2 <= size <= MAX_SUBGROUP_SIZE:
			frappe.throw(
				_("X-bar R Subgroup Size must be 0 (I-MR only) or between 2 and {0}").format(
					MAX_SUBGROUP_SIZE
				)
			)

		# Catch a missing certificate or a public private key when the settings are saved, not when
		# the gateway starts.
		security_config(self)
