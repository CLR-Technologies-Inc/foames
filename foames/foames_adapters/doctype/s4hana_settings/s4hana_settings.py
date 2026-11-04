# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters.s4hana.confirmations import MAX_ACTIVITIES
from foames.foames_adapters.s4hana.entities import DEFAULT_ENTITIES, EntitySpec, spec_from_override
from foames.foames_adapters.s4hana.odata import Connection, ODataClient, ODataError


class S4HANASettings(Document):
	def validate(self):
		seen = set()
		for row in self.entity_mappings:
			if row.reference_type in seen:
				frappe.throw(
					_("Row {0}: {1} is mapped twice").format(row.idx, frappe.bold(row.reference_type))
				)
			seen.add(row.reference_type)
			try:
				spec_from_override(row.as_dict())
			except ValueError as e:
				frappe.throw(_("Row {0}: {1}").format(row.idx, e))
		self.validate_rollup()

	def validate_rollup(self):
		if not self.roll_up_counts_to_confirmations:
			return
		if not (self.confirmation_unit or "").strip():
			frappe.throw(_("Set the Confirmation Unit the machine counts are confirmed in"))
		position = int(self.machine_time_activity_position or 0)
		if not 0 <= position <= MAX_ACTIVITIES:
			frappe.throw(_("Machine Time Activity Position must be between 0 and {0}").format(MAX_ACTIVITIES))

	def connection(self) -> Connection:
		return Connection(
			base_url=self.base_url or "",
			client=self.sap_client or "",
			auth=self.auth_method or "Basic",
			username=self.username or "",
			password=self.get_password("password", raise_exception=False) or "",
			token_url=self.token_url or "",
			client_id=self.client_id or "",
			client_secret=self.get_password("client_secret", raise_exception=False) or "",
			scope=self.scope or "",
			language=self.language or "EN",
			timeout=float(self.timeout or 30),
			cafile=self.ca_bundle or None,
		)

	def client(self, transport=None) -> ODataClient:
		return ODataClient(self.connection(), transport=transport)

	def entity_specs(self) -> dict[str, EntitySpec]:
		specs = dict(DEFAULT_ENTITIES)
		for row in self.entity_mappings:
			specs[row.reference_type] = spec_from_override(row.as_dict())
		return specs

	@frappe.whitelist()
	def test_connection(self):
		"""Fetch a CSRF token from the product service: proves the URL, client and credentials."""
		frappe.only_for("System Manager")
		service = self.entity_specs()["Item"].service
		try:
			self.client().csrf_token(service)
		except ODataError as e:
			frappe.throw(str(e), title=_("S/4HANA connection failed"))
		return _("Connected to {0}").format(self.base_url)


def get_settings() -> S4HANASettings:
	return frappe.get_cached_doc("S4HANA Settings")
