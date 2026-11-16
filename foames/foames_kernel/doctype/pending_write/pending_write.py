# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document


class PendingWrite(Document):
	"""A write a read-only connector wanted to make, waiting for an operator's electronic sign-off.

	Created by the write gate only. The record is changed only by the gate's own steps (sign-off,
	release, execution, withdrawal), which use db_set; a save from the desk or the REST API is refused.
	"""

	def validate(self):
		if not self.is_new() and not self.flags.ignore_permissions:
			frappe.throw(_("A Pending Write is changed only by signing it off"))

	def on_trash(self):
		frappe.throw(_("Pending Writes are part of the audit record and cannot be deleted"))
