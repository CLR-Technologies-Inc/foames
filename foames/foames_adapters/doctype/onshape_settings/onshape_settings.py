# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters.onshape.client import Connection, OnshapeClient


class OnshapeSettings(Document):
	def validate(self):
		if self.enabled:
			for field, label in (("base_url", _("Base URL")), ("access_key", _("Access Key"))):
				value = (self.get(field) or "").strip()
				if not value:
					frappe.throw(_("{0} is required when Onshape is enabled").format(label))
			if not (self.get("base_url") or "").lower().startswith("https://"):
				frappe.throw(_("Base URL must use https://, or the API secret would travel unencrypted"))

	def connection(self) -> Connection:
		return Connection(
			base_url=(self.base_url or "").strip(),
			access_key=(self.access_key or "").strip(),
			secret_key=self.get_password("secret_key", raise_exception=False) or "",
			timeout=float(self.timeout or 30),
		)

	def client(self, transport=None) -> OnshapeClient:
		return OnshapeClient(self.connection(), transport=transport)

	def allows_document(self, document_id: str) -> bool:
		"""Whether the configured scope permits reading this document."""
		allowed = {
			line.strip()
			for line in (self.allowed_documents or "").splitlines()
			if line.strip()
		}
		return not allowed or document_id in allowed

	@frappe.whitelist()
	def test_connection(self):
		"""Sign one request and read the API key's owner: proves URL, key pair and scopes."""
		frappe.only_for("System Manager")
		try:
			user = self.client().get_user()
		except Exception as e:
			frappe.throw(str(e), title=_("Onshape connection failed"))
		name = user.get("name") or user.get("emailAddress") or ""
		return _("Connected to {0}{1}").format(self.base_url, " as " + name if name else "")


def get_settings() -> OnshapeSettings:
	return frappe.get_cached_doc("Onshape Settings")
