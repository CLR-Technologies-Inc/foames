# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Scheduler entry points for the simulation module."""

from __future__ import annotations

import frappe

from foames.foames_simulation.client import ProviderClient, ProviderError
from foames.foames_simulation.simulation import epoch_to_datetime


def _settings():
	if not frappe.db.exists("DocType", "Simulation Settings"):
		return None
	return frappe.get_cached_doc("Simulation Settings")


def sync_runs() -> None:
	"""Hourly: pull provider status into local Simulation Run records.

	Does nothing unless Simulation Settings is enabled with a provider URL.
	Runs that finished since the last sync get their status, timestamps,
	residual summary and artifact list copied onto the record; a provider that
	is unreachable leaves records untouched rather than marking them failed.
	"""
	settings = _settings()
	if not settings or not settings.enabled or not (settings.provider_url or "").strip():
		return
	client = ProviderClient(
		base_url=settings.provider_url.strip(),
		token=settings.get_password("provider_token", raise_exception=False) or "",
		timeout=float(settings.timeout or 30),
	)
	for doc in frappe.get_all(
		"Simulation Run",
		filters={"status": ["in", ["draft", "queued", "running"]]},
		fields=["name", "run_id", "status"],
	):
		try:
			payload = client.get_run(doc.run_id)
		except ProviderError:
			continue
		run = payload.get("run") or {}
		status = run.get("status")
		if not status or status == doc.status:
			continue
		frappe.db.set_value(
			"Simulation Run",
			doc.name,
			{
				"status": status,
				"error": run.get("error") or "",
				"result_summary": frappe.as_json(run.get("result") or {}),
				"finished_on": epoch_to_datetime(run.get("finished_at")),
			},
			update_modified=False,
		)
