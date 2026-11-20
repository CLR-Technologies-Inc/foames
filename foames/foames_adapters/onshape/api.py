# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Whitelisted Onshape reads and CAD-reference linking.

Every method is read-only against Onshape: it signs GET requests and records the
result locally. Linking creates an `Onshape CAD Reference` document; it never
touches the linked FoaMES record and never calls a write API. Frappe permission
checks apply to the linked DocType through `frappe.has_permission`.
"""

from __future__ import annotations

import frappe
from frappe import _

from foames.foames_adapters.doctype.onshape_settings.onshape_settings import get_settings
from foames.foames_adapters.onshape import model
from foames.foames_adapters.onshape.client import OnshapeError

READ_ROLES = ("System Manager", "FoaMES Engineer", "FoaMES Quality", "FoaMES Supervisor", "FoaMES Integration")


def _require_enabled():
	settings = get_settings()
	if not settings or not settings.enabled:
		frappe.throw(_("Onshape is not enabled in Onshape Settings"), frappe.PermissionError)
	return settings


def _check_document_scope(settings, document_id: str):
	if document_id and not settings.allows_document(document_id):
		frappe.throw(
			_("Document {0} is outside the configured Onshape scope").format(document_id),
			frappe.PermissionError,
		)


@frappe.whitelist()
def test_connection() -> str:
	"""Desk button on Onshape Settings; same check as the document method."""
	settings = _require_enabled()
	return settings.test_connection()


@frappe.whitelist()
def search_documents(query: str = "", limit: int = 25) -> list[dict]:
	"""List documents the API key can see, for the link dialog. Read-only."""
	frappe.only_for(READ_ROLES)
	settings = _require_enabled()
	try:
		items = settings.client().list_documents(limit=max(1, min(int(limit or 25), 100)))
	except OnshapeError as e:
		frappe.throw(str(e), title=_("Onshape read failed"))
	needle = (query or "").strip().lower()
	out = []
	for item in items:
		if not isinstance(item, dict):
			continue
		did = item.get("id") or ""
		if not settings.allows_document(did):
			continue
		name = item.get("name") or ""
		if needle and needle not in name.lower() and needle not in did.lower():
			continue
		out.append({"id": did, "name": name, "url": model.canonical_url(settings.base_url, _doc_stub(did, item))})
		if len(out) >= 50:
			break
	return out


def _doc_stub(did: str, item: dict) -> model.CadReference:
	ws = (item.get("defaultWorkspace") or {}).get("id") or ""
	return model.CadReference(kind="Document", document_id=did, wvm_type="w" if ws else "v",
	                          wvm_id=ws or (item.get("version") or {}).get("id") or did)


@frappe.whitelist()
def get_document(document_id: str) -> dict:
	"""One document's metadata as a CadReference dict, for the link dialog preview."""
	frappe.only_for(READ_ROLES)
	settings = _require_enabled()
	_check_document_scope(settings, document_id)
	try:
		ref = settings.client().document_reference(document_id, settings.base_url)
	except OnshapeError as e:
		frappe.throw(str(e), title=_("Onshape read failed"))
	return ref.to_dict()


@frappe.whitelist()
def link_reference(
	target_doctype: str,
	target_name: str,
	document_id: str,
	wvm_type: str = "w",
	wvm_id: str = "",
	element_id: str = "",
	part_id: str = "",
	configuration: str = "",
	kind: str = "Document",
	title: str = "",
) -> str:
	"""Create an Onshape CAD Reference from a FoaMES record to a design.

	The caller must be able to read the target record; the reference is stored
	against it and shows in the record's CAD panel. `wvm_type` `v` or `m` pins the
	reference to an immutable revision; `w` marks unreleased workspace state.
	"""
	frappe.only_for(("System Manager", "FoaMES Engineer", "FoaMES Integration"))
	settings = _require_enabled()
	_check_document_scope(settings, document_id)
	if not frappe.db.exists(target_doctype, target_name):
		frappe.throw(_("{0} {1} does not exist").format(target_doctype, target_name), frappe.DoesNotExistError)
	if not frappe.has_permission(target_doctype, "read", target_name):
		frappe.throw(_("You cannot read {0} {1}").format(target_doctype, target_name), frappe.PermissionError)
	try:
		ref = model.CadReference(
			kind=kind,
			document_id=document_id,
			wvm_type=wvm_type,
			wvm_id=wvm_id,
			title=title,
			element_id=element_id,
			part_id=part_id,
			configuration=configuration,
		)
	except ValueError as e:
		frappe.throw(str(e))
	if not ref.canonical_url:
		ref = model.CadReference(
			kind=ref.kind, document_id=ref.document_id, wvm_type=ref.wvm_type, wvm_id=ref.wvm_id,
			title=ref.title, element_id=ref.element_id, part_id=ref.part_id,
			configuration=ref.configuration, canonical_url=model.canonical_url(settings.base_url, ref),
		)
	doc = frappe.get_doc(
		{
			"doctype": "Onshape CAD Reference",
			"title": title or "{0} {1}".format(kind, document_id),
			"link_doctype": target_doctype,
			"link_name": target_name,
			"reference_kind": ref.kind,
			"wvm_type": ref.wvm_type,
			"wvm_id": ref.wvm_id,
			"document_id": ref.document_id,
			"element_id": ref.element_id,
			"part_id": ref.part_id,
			"configuration": ref.configuration,
			"canonical_url": ref.canonical_url,
			"status": "Linked",
			"last_synced_on": frappe.utils.now_datetime(),
		}
	)
	doc.insert(ignore_permissions=False)
	return doc.name


@frappe.whitelist()
def get_references(target_doctype: str, target_name: str) -> list[dict]:
	"""The CAD references panel data for one FoaMES record."""
	frappe.only_for(READ_ROLES)
	if not frappe.has_permission(target_doctype, "read", target_name):
		frappe.throw(_("You cannot read {0} {1}").format(target_doctype, target_name), frappe.PermissionError)
	rows = frappe.get_all(
		"Onshape CAD Reference",
		filters={"link_doctype": target_doctype, "link_name": target_name},
		fields=["name", "title", "reference_kind", "status", "wvm_type", "wvm_id", "document_id",
				"element_id", "part_id", "configuration", "pinned", "canonical_url", "source_revision",
				"last_synced_on"],
		order_by="creation desc",
	)
	for row in rows:
		row["revision_label"] = "Unreleased workspace" if row.get("wvm_type") == "w" else "{0} {1}".format(
			(row.get("wvm_type") or "").upper(), row.get("wvm_id") or ""
		).strip()
	return rows
