# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from foames.foames_mes.spc import MAX_SUBGROUP_SIZE


class MachineDataSettings(Document):
	def validate(self):
		size = cint(self.get("spc_subgroup_size"))
		if size and not 2 <= size <= MAX_SUBGROUP_SIZE:
			frappe.throw(
				_("X-bar R Subgroup Size must be 0 (I-MR only) or between 2 and {0}").format(
					MAX_SUBGROUP_SIZE
				)
			)
