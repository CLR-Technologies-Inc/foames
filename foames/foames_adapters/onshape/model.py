# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""CAD reference values: what a FoaMES record points at in Onshape, and whether that point is pinned.

Onshape addresses a design three ways: a mutable workspace (`w`), an immutable
version (`v`) and an immutable microversion (`m`). A production record must be
able to pin itself to a `v` or `m`; a `w` reference is explicitly *unreleased
workspace* state that a later design change can move. This module holds that
rule and the parsing of Onshape's JSON into plain values. It imports nothing
from Frappe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlsplit

# Onshape's workspace/version/microversion selector letters.
WVM_WORKSPACE = "w"
WVM_VERSION = "v"
WVM_MICROVERSION = "m"
WVM_TYPES = (WVM_WORKSPACE, WVM_VERSION, WVM_MICROVERSION)
PINNED_WVM_TYPES = (WVM_VERSION, WVM_MICROVERSION)

KINDS = ("Document", "Part", "Assembly", "Drawing")

DEFAULT_BASE_URL = "https://cad.onshape.com"

# Onshape document URLs look like:
#   https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}
#   https://cad.onshape.com/documents/{did}/v/{vid}/e/{eid}
#   https://cad.onshape.com/documents/{did}/m/{mvid}/e/{eid}
# with optional /partstudios/... or drawing paths after the element id.
_DOCUMENT_URL = re.compile(
	r"^/documents/(?P<did>[^/]+)/(?P<wvm>[wvm])/(?P<wvm_id>[^/]+)(?:/e/(?P<eid>[^/]+))?"
)


@dataclass(frozen=True)
class CadReference:
	"""One linkable reference from a FoaMES record to Onshape design data.

	`wvm_type`/`wvm_id` select the mutable workspace or a pinned version or
	microversion; `element_id` names the part studio, assembly or drawing inside
	the document when the reference is narrower than the whole document.
	"""

	kind: str
	document_id: str
	wvm_type: str
	wvm_id: str
	title: str = ""
	element_id: str = ""
	part_id: str = ""
	configuration: str = ""
	canonical_url: str = ""
	extra: dict = field(default_factory=dict)

	def __post_init__(self):
		if self.kind not in KINDS:
			raise ValueError(f"Unknown CAD reference kind {self.kind!r}")
		if self.wvm_type not in WVM_TYPES:
			raise ValueError(f"Unknown workspace/version/microversion type {self.wvm_type!r}")
		if not self.document_id or not self.wvm_id:
			raise ValueError("A CAD reference needs a document id and a workspace/version/microversion id")

	@property
	def pinned(self) -> bool:
		"""True when the reference names an immutable version or microversion."""
		return self.wvm_type in PINNED_WVM_TYPES

	@property
	def mutable(self) -> bool:
		return self.wvm_type == WVM_WORKSPACE

	@property
	def revision_label(self) -> str:
		"""Short human label: pinned references show their version, workspaces say so."""
		if self.wvm_type == WVM_WORKSPACE:
			return "Unreleased workspace"
		return f"{self.wvm_type.upper()} {self.wvm_id}"

	def api_path(self) -> str:
		"""The document-scoped API path prefix for this reference."""
		return "/api/documents/d/{0}/{1}/{2}".format(self.document_id, self.wvm_type, self.wvm_id)

	def to_dict(self) -> dict:
		return {
			"kind": self.kind,
			"document_id": self.document_id,
			"wvm_type": self.wvm_type,
			"wvm_id": self.wvm_id,
			"title": self.title,
			"element_id": self.element_id,
			"part_id": self.part_id,
			"configuration": self.configuration,
			"canonical_url": self.canonical_url,
			"pinned": self.pinned,
			"revision_label": self.revision_label,
			"extra": dict(self.extra),
		}


def parse_onshape_url(url: str) -> dict | None:
	"""Extract the document id, wvm selector and element id from an Onshape URL.

	Accepts the browser URLs (`/documents/did/w/wid/e/eid`) and returns None for
	anything that is not a document URL on the configured host. Query strings and
	fragments are ignored; other path segments after the element id are kept out.
	"""
	parts = urlsplit(url.strip())
	match = _DOCUMENT_URL.match(parts.path)
	if not match:
		return None
	return {
		"document_id": match.group("did"),
		"wvm_type": match.group("wvm"),
		"wvm_id": match.group("wvm_id"),
		"element_id": match.group("eid") or "",
	}


def canonical_url(base_url: str, reference: CadReference) -> str:
	"""The browser URL a user opens to see this reference in Onshape."""
	path = "/documents/{0}/{1}/{2}".format(reference.document_id, reference.wvm_type, reference.wvm_id)
	if reference.element_id:
		path += "/e/" + quote(reference.element_id, safe="")
	return base_url.rstrip("/") + path


def _text(value) -> str:
	return str(value).strip() if value is not None else ""


def parse_document(payload: dict, base_url: str = DEFAULT_BASE_URL) -> CadReference:
	"""A document GET response into a Document-kind CadReference.

	Reads the default workspace (`w`) and version (`v`) ids Onshape returns; the
	microversion is only known for documents that have one. Missing fields leave
	empties rather than failing, so a partial response still links.
	"""
	default_ws = payload.get("defaultWorkspace") or {}
	version = payload.get("version") or {}
	wvm_type, wvm_id = WVM_WORKSPACE, _text(default_ws.get("id"))
	if not wvm_id and version.get("id"):
		wvm_type, wvm_id = WVM_VERSION, _text(version.get("id"))
	microversions = payload.get("microversions") or []
	if microversions and isinstance(microversions[0], dict) and microversions[0].get("id"):
		# Prefer the newest microversion when the document has them: it is immutable.
		wvm_type, wvm_id = WVM_MICROVERSION, _text(microversions[0].get("id"))
	ref = CadReference(
		kind="Document",
		document_id=_text(payload.get("id")),
		wvm_type=wvm_type or WVM_WORKSPACE,
		wvm_id=wvm_id,
		title=_text(payload.get("name")),
	)
	return _with_url(ref, base_url)


def parse_element(payload: dict, base_url: str = DEFAULT_BASE_URL, kind: str = "Part") -> CadReference:
	"""An element (part studio, assembly or drawing) response into a CadReference.

	Element GETs return the element id and name; the document and wvm selector
	come from the request path the caller used, passed in via `extra` by the
	client. Only fields actually present are copied.
	"""
	extra = payload.get("_foames_context") or {}
	ref = CadReference(
		kind=kind if kind in KINDS else "Part",
		document_id=_text(extra.get("document_id")),
		wvm_type=_text(extra.get("wvm_type")) or WVM_WORKSPACE,
		wvm_id=_text(extra.get("wvm_id")),
		title=_text(payload.get("name")) or _text(payload.get("elementName")),
		element_id=_text(payload.get("id")) or _text(payload.get("elementId")),
		part_id=_text(payload.get("partId")) or _text(payload.get("part_id")),
		configuration=_text(payload.get("configuration")),
		extra={k: v for k, v in extra.items() if k not in ("document_id", "wvm_type", "wvm_id")},
	)
	return _with_url(ref, base_url)


def _with_url(ref: CadReference, base_url: str) -> CadReference:
	if ref.canonical_url or not ref.document_id or not ref.wvm_id:
		return ref
	return CadReference(
		kind=ref.kind,
		document_id=ref.document_id,
		wvm_type=ref.wvm_type,
		wvm_id=ref.wvm_id,
		title=ref.title,
		element_id=ref.element_id,
		part_id=ref.part_id,
		configuration=ref.configuration,
		canonical_url=canonical_url(base_url, ref),
		extra=ref.extra,
	)


def parse_bom_rows(payload) -> list[dict]:
	"""Rows of an assembly/BOM structure response, kept flat and provenance-carrying.

	Only rows that carry a part identity are kept; each row keeps the source ids
	Onshape returned so a later reconciliation can tell a geometric assembly row
	from an approved manufacturing BOM line. Items without ids are skipped rather
	than guessed.
	"""
	rows = []
	for item in payload or []:
		if not isinstance(item, dict):
			continue
		part_id = _text(item.get("partId") or item.get("part_id"))
		if not part_id:
			continue
		rows.append(
			{
				"part_id": part_id,
				"name": _text(item.get("name")),
				"part_number": _text(item.get("partNumber") or item.get("part_number")),
				"quantity": item.get("quantity"),
				"configuration": _text(item.get("configuration")),
				"revision": _text(item.get("revision") or item.get("version")),
				"source": "onshape",
			}
		)
	return rows


def unquote_element_id(element_id: str) -> str:
	return unquote(element_id)
