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
from frappe.query_builder.functions import Max


def execute():
	"""Fill Machine.last_count_at from the Count events recorded before the field existed."""
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.machine, Max(event.timestamp).as_("last"))
		.where(event.event_type == "Count")
		.groupby(event.machine)
		.run(as_dict=True)
	)
	for row in rows:
		frappe.db.set_value("Machine", row.machine, "last_count_at", row.last, update_modified=False)
