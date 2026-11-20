# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters.onshape import model
from foames.foames_adapters.onshape.client import OnshapeAuthError, OnshapeError
from foames.foames_adapters.onshape.model import PINNED_WVM_TYPES


class OnshapeCADReference(Document):
	def validate(self):
		if self.wvm_type not in model.WVM_TYPES:
			frappe.throw(_("Workspace / Version / Microversion must be w, v or m"))
		# Pinned is derived, never set by hand: a version or microversion is immutable,
		# a workspace is unreleased state that a later design change can move.
		self.pinned = 1 if self.wvm_type in PINNED_WVM_TYPES else 0
		self.canonical_url = model.canonical_url(_base_url(), self.to_reference())

	def to_reference(self) -> model.CadReference:
		return model.CadReference(
			kind=self.reference_kind or "Document",
			document_id=self.document_id or "",
			wvm_type=self.wvm_type or "w",
			wvm_id=self.wvm_id or "",
			title=self.title or "",
			element_id=self.element_id or "",
			part_id=self.part_id or "",
			configuration=self.configuration or "",
		)

	@frappe.whitelist()
	def refresh(self):
		"""Re-read the document from Onshape and update sync state. Read-only upstream."""
		frappe.only_for(("System Manager", "FoaMES Engineer", "FoaMES Integration"))
		settings = _settings()
		if not settings or not settings.enabled:
			frappe.throw(_("Onshape is not enabled in Onshape Settings"))
		if not settings.allows_document(self.document_id):
			frappe.throw(_("Document {0} is outside the configured Onshape scope").format(self.document_id))
		try:
			payload = settings.client().get_document(self.document_id)
		except OnshapeAuthError as e:
			self.db_set("status", "Inaccessible", update_modified=False)
			frappe.throw(str(e), title=_("Onshape authorization failed"))
		except OnshapeError as e:
			self.db_set("status", "Stale", update_modified=False)
			frappe.throw(str(e), title=_("Onshape refresh failed"))
		if not payload.get("id"):
			self.db_set("status", "Inaccessible", update_modified=False)
			frappe.throw(_("Onshape no longer returns document {0}").format(self.document_id))
		# A pinned reference never moves: if the design has a newer version, the reference
		# is marked Superseded for a person to decide, not silently re-pointed.
		version = (payload.get("version") or {}).get("id")
		if self.wvm_type in PINNED_WVM_TYPES and version and version != self.wvm_id:
			self.db_set("status", "Superseded", update_modified=False)
		else:
			self.db_set("status", "Linked", update_modified=False)
		self.db_set("last_synced_on", frappe.utils.now_datetime(), update_modified=False)
		if payload.get("name") and payload["name"] != self.title:
			self.db_set("title", payload["name"], update_modified=False)
		return _("Refreshed {0}").format(self.name)


def _settings():
	if not frappe.db.exists("DocType", "Onshape Settings"):
		return None
	return frappe.get_cached_doc("Onshape Settings")


def _base_url() -> str:
	settings = _settings()
	return (settings.base_url if settings else "") or model.DEFAULT_BASE_URL
