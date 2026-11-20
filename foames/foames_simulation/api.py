# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Whitelisted simulation provider calls.

Submitting a run is an explicit, permissioned action (FoaMES Engineer or
Supervisor); reads are wider (Quality included, for evidence review). A CFD
job never writes to plant equipment, SCADA or an ERP — the provider only runs
solver commands in its own container.
"""

from __future__ import annotations

import frappe
from frappe import _

from foames.foames_simulation.client import ProviderClient, ProviderError

WRITE_ROLES = ("System Manager", "FoaMES Engineer", "FoaMES Supervisor")
READ_ROLES = WRITE_ROLES + ("FoaMES Quality", "FoaMES Integration")


def _settings():
	if not frappe.db.exists("DocType", "Simulation Settings"):
		return None
	return frappe.get_cached_doc("Simulation Settings")


def _client(transport=None) -> ProviderClient:
	settings = _settings()
	if not settings or not settings.enabled or not (settings.provider_url or "").strip():
		frappe.throw(_("Simulation is not enabled in Simulation Settings"), frappe.PermissionError)
	return ProviderClient(
		base_url=settings.provider_url.strip(),
		token=settings.get_password("provider_token", raise_exception=False) or "",
		timeout=float(settings.timeout or 30),
		transport=transport,
	)


@frappe.whitelist()
def simulation_cases() -> list:
	"""The cases the provider offers, for pickers."""
	frappe.only_for(READ_ROLES)
	try:
		return _client().cases()
	except ProviderError as e:
		frappe.throw(str(e), title=_("Simulation provider unreachable"))


@frappe.whitelist()
def simulation_submit(manifest: str | dict, requester: str = "") -> str:
	"""Submit a case manifest; returns the local Simulation Run name.

	`manifest` may be a JSON string or object: {"case": "pitzdaily", "params": {...}}.
	The provider dedupes on the manifest's idempotency key, so a retry after a
	timeout returns the same run rather than launching a duplicate job.
	"""
	frappe.only_for(WRITE_ROLES)
	if isinstance(manifest, str):
		import json

		try:
			manifest = json.loads(manifest)
		except ValueError:
			frappe.throw(_("manifest is not valid JSON"))
	if not isinstance(manifest, dict) or not manifest.get("case"):
		frappe.throw(_("manifest needs a 'case'"))
	try:
		response = _client().submit(manifest, requester=requester or frappe.session.user)
	except ProviderError as e:
		frappe.throw(str(e), title=_("Simulation submit failed"))
	provider_run = response.get("run") or {}
	existing = frappe.db.exists("Simulation Run", {"run_id": provider_run.get("run_id")})
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Simulation Run",
			"run_id": provider_run.get("run_id"),
			"case": manifest.get("case"),
			"status": provider_run.get("status") or "queued",
			"solver": provider_run.get("solver") or "",
			"solver_version": provider_run.get("solver_version") or "",
			"config_hash": provider_run.get("config_hash") or "",
			"requester": provider_run.get("requester") or requester or frappe.session.user,
			"manifest": frappe.as_json(manifest),
		}
	)
	doc.insert(ignore_permissions=False)
	return doc.name


@frappe.whitelist()
def simulation_status(run_name: str) -> dict:
	"""Live status of one Simulation Run from the provider."""
	frappe.only_for(READ_ROLES)
	doc = frappe.get_doc("Simulation Run", run_name)
	frappe.has_permission("Simulation Run", "read", doc, throw=True)
	try:
		response = _client().get_run(doc.run_id)
	except ProviderError as e:
		frappe.throw(str(e), title=_("Simulation provider unreachable"))
	return response.get("run") or {}


@frappe.whitelist()
def simulation_cancel(run_name: str) -> str:
	"""Ask the provider to cancel a queued or running Simulation Run."""
	frappe.only_for(WRITE_ROLES)
	doc = frappe.get_doc("Simulation Run", run_name)
	frappe.has_permission("Simulation Run", "write", doc, throw=True)
	try:
		_client().cancel(doc.run_id)
	except ProviderError as e:
		frappe.throw(str(e), title=_("Simulation cancel failed"))
	return _("Cancel requested for {0}").format(doc.name)
