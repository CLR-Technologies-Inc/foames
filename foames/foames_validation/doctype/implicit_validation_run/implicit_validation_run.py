# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""One implicit validation run: the evidence bundle of `foames_validation/implicit.py`, stored once.

A run is created only by `implicit_api.run_implicit_validation`, which evaluates the checks itself;
nobody can create one on the desk or write a result into it. After insert nothing in it changes, and
it is never deleted, so a gate that reads it by ID reads the evidence as it was produced.
"""

import frappe
from frappe import _
from frappe.model.document import Document

IMMUTABLE = (
	"definition_name",
	"definition_version",
	"outcome",
	"trigger",
	"environment",
	"machine",
	"configuration_revision",
	"as_of",
	"requested_by",
	"dataset_reference",
	"dataset_source",
	"input_hash",
	"result_hash",
	"summary",
	"definition",
	"result",
)


class ImplicitValidationRun(Document):
	def validate(self):
		if self.is_new():
			if not self.flags.from_evaluator:
				frappe.throw(
					_("Implicit validation runs are created by running the checks"), frappe.PermissionError
				)
			return
		before = self.get_doc_before_save()
		changed = [field for field in IMMUTABLE if before and before.get(field) != self.get(field)]
		if changed:
			frappe.throw(
				_("Implicit validation evidence cannot be changed ({0})").format(", ".join(changed)),
				frappe.PermissionError,
			)

	def on_trash(self):
		frappe.throw(_("Implicit validation evidence is kept; it cannot be deleted"), frappe.PermissionError)
