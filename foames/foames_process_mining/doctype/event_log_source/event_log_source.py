# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A field map that turns any DocType's records into process-mining events.

The source DocType is named as text, never linked, so an ERP record type (a Job Card, a Work
Order, an S/4HANA confirmation mirrored by the adapter) can be mined without the core depending
on it. See foames.foames_process_mining.extractors.extract_from_mapping for the semantics.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_process_mining.extractors import extract_from_mapping


class EventLogSource(Document):
	def validate(self):
		if not self.activity_field and not self.fixed_activity:
			frappe.throw(_("Set an Activity Field or a Fixed Activity"))
		if self.filters:
			try:
				parsed = json.loads(self.filters)
			except ValueError:
				frappe.throw(_("Filters must be valid JSON"))
			if not isinstance(parsed, dict | list):
				frappe.throw(_("Filters must be a JSON object or list"))
		if frappe.db.exists("DocType", self.source_doctype):
			self.check_fields()

	def check_fields(self):
		meta = frappe.get_meta(self.source_doctype)
		valid = {df.fieldname for df in meta.fields} | {
			"name",
			"owner",
			"creation",
			"modified",
			"modified_by",
		}
		wanted = {self.case_field, self.timestamp_field}
		for fieldname in (self.activity_field, self.end_timestamp_field, self.resource_field):
			if fieldname:
				wanted.add(fieldname)
		for part in (self.attribute_fields or "").split(","):
			if part.strip():
				wanted.add(part.strip())
		for part in (self.object_fields or "").split(","):
			if part.strip():
				wanted.add(part.split("=", 1)[-1].strip())
		unknown = sorted(f for f in wanted if f not in valid)
		if unknown:
			frappe.throw(_("{0} has no field named {1}").format(self.source_doctype, ", ".join(unknown)))

	def mapping(self) -> dict:
		return {
			"source_doctype": self.source_doctype,
			"case_field": self.case_field,
			"activity_field": self.activity_field,
			"fixed_activity": self.fixed_activity,
			"timestamp_field": self.timestamp_field,
			"end_timestamp_field": self.end_timestamp_field,
			"resource_field": self.resource_field,
			"filters": self.filters,
			"attribute_fields": self.attribute_fields,
			"object_fields": self.object_fields,
		}

	def extract(self, since=None, until=None):
		"""Events from this source in the window. Empty when the DocType is not installed."""
		return list(extract_from_mapping(self.mapping(), since, until))

	@frappe.whitelist()
	def preview(self, limit: int = 20) -> dict:
		"""The first events this source yields, for checking a mapping from the form."""
		frappe.has_permission("Event Log Source", "read", throw=True)
		installed = bool(frappe.db.exists("DocType", self.source_doctype))
		events = self.extract() if installed else []
		return {
			"installed": installed,
			"events": [e.__dict__ | {"timestamp": e.timestamp.isoformat()} for e in events[: int(limit)]],
			"total": len(events),
		}
