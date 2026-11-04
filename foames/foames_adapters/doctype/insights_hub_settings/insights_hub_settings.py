# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters.insights_hub.entities import DEFAULT_ENTITIES, EntitySpec, spec_from_override
from foames.foames_adapters.insights_hub.production import (
	DEFAULT_PROPERTY_SET,
	DEFAULT_VARIABLES,
	RollUpOptions,
)
from foames.foames_adapters.insights_hub.rest import (
	SERVICE_CREDENTIALS,
	TOKEN_MANAGER,
	Connection,
	InsightsHubError,
	RestClient,
)

VARIABLE_FIELDS = {
	"good": "good_variable",
	"scrap": "scrap_variable",
	"run_minutes": "run_minutes_variable",
	"window_minutes": "window_minutes_variable",
	"job": "job_variable",
	"state": "state_variable",
}


class InsightsHubSettings(Document):
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
		self.validate_auth()
		self.validate_rollup()

	def validate_auth(self):
		if not self.enabled:
			return
		if self.auth_method == SERVICE_CREDENTIALS and not (self.token_url or "").strip():
			frappe.throw(_("Service Credentials need the tenant's Token URL"))
		if self.auth_method == TOKEN_MANAGER and not (self.app_name or "").strip():
			frappe.throw(_("The Technical Token Manager needs the registered Application Name"))

	def validate_rollup(self):
		if not self.send_machine_data:
			return
		if not (self.property_set or "").strip():
			frappe.throw(_("Set the Aspect (property set) the machine records are written to"))
		names = [(self.get(field) or "").strip() for field in VARIABLE_FIELDS.values()]
		if len({name for name in names if name}) != len([name for name in names if name]):
			frappe.throw(_("Two aspect variables have the same name"))

	def connection(self) -> Connection:
		return Connection(
			gateway_url=(self.gateway_url or "").strip(),
			tenant=(self.tenant or "").strip(),
			auth=self.auth_method or TOKEN_MANAGER,
			client_id=self.client_id or "",
			client_secret=self.get_password("client_secret", raise_exception=False) or "",
			app_name=self.app_name or "",
			app_version=self.app_version or "",
			host_tenant=self.host_tenant or "",
			user_tenant=self.user_tenant or "",
			token_url=(self.token_url or "").strip(),
			timeout=float(self.timeout or 30),
			cafile=self.ca_bundle or None,
		)

	def client(self, transport=None) -> RestClient:
		return RestClient(self.connection(), transport=transport)

	def entity_specs(self) -> dict[str, EntitySpec]:
		specs = dict(DEFAULT_ENTITIES)
		for row in self.entity_mappings:
			specs[row.reference_type] = spec_from_override(row.as_dict())
		return specs

	def rollup_options(self, tz=None) -> RollUpOptions:
		variables = {
			key: (self.get(field) or "").strip() or DEFAULT_VARIABLES[key]
			for key, field in VARIABLE_FIELDS.items()
		}
		return RollUpOptions(
			property_set=(self.property_set or "").strip() or DEFAULT_PROPERTY_SET, variables=variables, tz=tz
		)

	@frappe.whitelist()
	def test_connection(self):
		"""Fetch a token and read one asset: proves the gateway, the tenant and the credentials."""
		frappe.only_for("System Manager")
		spec = self.entity_specs()["Workstation"]
		try:
			self.client().get_page(spec.path(), size=1)
		except InsightsHubError as e:
			frappe.throw(str(e), title=_("Insights Hub connection failed"))
		return _("Connected to {0}").format(self.gateway_url)


def get_settings() -> InsightsHubSettings:
	return frappe.get_cached_doc("Insights Hub Settings")
