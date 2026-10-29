# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_adapters import AdapterError, get_adapter, get_adapters


class ExternalReference(Document):
	"""A pointer to a record in an ERP, resolved through that ERP's adapter.

	Kernel and MES records refer to ERP data only through External References, which keeps the
	core independent of any one ERP.
	"""

	def validate(self):
		self.validate_adapter()
		self.validate_unique()
		if not self.flags.resolved and not frappe.db.get_single_value(
			"FoaMES Settings", "skip_resolution_on_save"
		):
			self.resolve_if_available()

	def validate_adapter(self):
		adapters = get_adapters()
		adapter = adapters.get(self.erp_system)
		if not adapter:
			frappe.throw(
				_("{0} is not a registered ERP system. Registered: {1}").format(
					frappe.bold(self.erp_system), ", ".join(adapters) or _("none")
				)
			)
		if not adapter.supports(self.reference_type):
			frappe.throw(
				_("{0} does not support reference type {1}").format(
					adapter.label, frappe.bold(self.reference_type)
				)
			)

	def validate_unique(self):
		duplicate = frappe.db.exists(
			"External Reference",
			{
				"erp_system": self.erp_system,
				"reference_type": self.reference_type,
				"external_id": self.external_id,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("{0} {1} in {2} is already referenced by {3}").format(
					self.reference_type, frappe.bold(self.external_id), self.erp_system, duplicate
				),
				frappe.DuplicateEntryError,
			)

	def resolve_if_available(self):
		if get_adapter(self.erp_system).is_available():
			self.resolve_from_erp()

	def resolve_from_erp(self):
		resolved = get_adapter(self.erp_system).resolve(self.reference_type, self.external_id)
		self.last_resolved_on = now_datetime()
		if resolved:
			self.status = "Resolved"
			self.label = resolved.label
		else:
			self.status = "Missing"
			self.label = None

	@frappe.whitelist()
	def resolve(self):
		"""Look the record up in its ERP now and save the result."""
		try:
			self.resolve_from_erp()
		except AdapterError as e:
			frappe.throw(str(e))
		# Already resolved above; don't look the record up again in validate.
		self.flags.resolved = True
		try:
			self.save()
		finally:
			self.flags.resolved = False
		return self.status


def get_reference(erp_system: str, reference_type: str, external_id: str) -> str:
	"""Name of the External Reference for this ERP record, creating it when it does not exist yet."""
	name = frappe.db.exists(
		"External Reference",
		{"erp_system": erp_system, "reference_type": reference_type, "external_id": external_id},
	)
	if name:
		return name
	doc = frappe.get_doc(
		{
			"doctype": "External Reference",
			"erp_system": erp_system,
			"reference_type": reference_type,
			"external_id": external_id,
		}
	).insert()
	return doc.name
