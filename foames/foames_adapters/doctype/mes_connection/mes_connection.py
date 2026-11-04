# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters.mes.adapter import ProfileAdapter
from foames.foames_adapters.mes.entities import spec_from_override
from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import (
	AUTH_API_KEY,
	AUTH_BASIC,
	AUTH_BEARER,
	AUTH_METHODS,
	AUTH_OAUTH,
	Connection,
	MESError,
	RestClient,
)


def profiles() -> dict[str, Profile]:
	"""The profiles of every registered MES adapter, by key."""
	from foames.foames_adapters import get_adapters

	return {
		key: adapter.profile for key, adapter in get_adapters().items() if isinstance(adapter, ProfileAdapter)
	}


def parse_headers(text: str) -> dict:
	"""`Name: value` lines into a dict."""
	headers = {}
	for line in (text or "").splitlines():
		line = line.strip()
		if not line:
			continue
		name, sep, value = line.partition(":")
		if not sep or not name.strip():
			raise ValueError(_("{0} is not a Name: value header").format(line))
		headers[name.strip()] = value.strip()
	return headers


class MESConnection(Document):
	"""How FoaMES reaches one MES; one record per registered adapter, named after its key."""

	def validate(self):
		known = profiles()
		if self.adapter not in known:
			frappe.throw(
				_("{0} is not a registered MES adapter. Registered: {1}").format(
					frappe.bold(self.adapter), ", ".join(known) or _("none")
				)
			)
		profile = known[self.adapter]
		self.profile_notes = profile.notes
		self.documentation_url = profile.docs_url
		if self.auth_method not in AUTH_METHODS:
			frappe.throw(_("Unknown authentication method {0}").format(frappe.bold(self.auth_method)))
		if self.auth_method not in profile.auth_methods:
			frappe.msgprint(
				_(
					"{0} is not an authentication method {1} documents; it may still work on your installation."
				).format(self.auth_method, profile.label),
				indicator="orange",
			)
		if self.auth_method == AUTH_API_KEY and not (self.api_key_header or "").strip():
			self.api_key_header = profile.api_key_header or "X-API-Key"
		if self.enabled:
			self.validate_credentials()
		try:
			parse_headers(self.extra_headers)
		except ValueError as e:
			frappe.throw(str(e))
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

	def validate_credentials(self):
		if self.auth_method == AUTH_OAUTH and not (self.token_url or "").strip():
			frappe.throw(_("OAuth 2.0 client credentials need a Token URL"))
		if self.auth_method == AUTH_BASIC and not (self.username or "").strip():
			frappe.throw(_("Basic authentication needs a Username"))
		if self.auth_method == AUTH_BEARER and not self.get_password("token", raise_exception=False):
			frappe.throw(_("Bearer Token authentication needs the Token"))
		if self.auth_method == AUTH_API_KEY and not self.get_password("api_key", raise_exception=False):
			frappe.throw(_("API Key Header authentication needs the API Key"))

	@property
	def profile(self) -> Profile:
		return profiles()[self.adapter]

	def connection(self) -> Connection:
		headers = dict(self.profile.headers)
		headers.update(parse_headers(self.extra_headers))
		return Connection(
			base_url=(self.base_url or "").strip(),
			auth=self.auth_method or self.profile.default_auth,
			username=self.username or "",
			password=self.get_password("password", raise_exception=False) or "",
			token=self.get_password("token", raise_exception=False) or "",
			api_key=self.get_password("api_key", raise_exception=False) or "",
			api_key_header=(self.api_key_header or self.profile.api_key_header or "X-API-Key").strip(),
			token_url=(self.token_url or "").strip(),
			client_id=self.client_id or "",
			client_secret=self.get_password("client_secret", raise_exception=False) or "",
			scope=self.scope or "",
			site=(self.site or "").strip(),
			headers=headers,
			timeout=float(self.timeout or 30),
			cafile=self.ca_bundle or None,
		)

	def client(self, transport=None) -> RestClient:
		return RestClient(self.connection(), transport=transport)

	@frappe.whitelist()
	def test_connection(self):
		"""Call the Test Path (or the base URL) once: proves the URL, the credentials and the headers."""
		frappe.only_for("System Manager")
		path = (self.test_path or "").strip()
		try:
			self.client().get(path)
		except MESError as e:
			frappe.throw(str(e), title=_("{0} connection failed").format(self.profile.label))
		return _("Connected to {0}").format(self.base_url)


def enabled_connections() -> list[MESConnection]:
	names = frappe.get_all("MES Connection", {"enabled": 1, "outbox_paused": 0}, pluck="name")
	return [frappe.get_cached_doc("MES Connection", name) for name in names if name in profiles()]
