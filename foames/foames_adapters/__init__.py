# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Registry of ERP adapters declared through the `foames_erp_adapters` hook."""

import frappe

from foames.foames_adapters.base import (
	REFERENCE_TYPES,
	AdapterError,
	AdapterUnavailable,
	ERPAdapter,
	ResolvedReference,
	UnsupportedReferenceType,
)


def get_adapters() -> dict[str, ERPAdapter]:
	"""All registered adapters keyed by their `key`, whether or not their ERP is installed."""
	adapters = {}
	for path in frappe.get_hooks("foames_erp_adapters"):
		adapter = frappe.get_attr(path)()
		adapters[adapter.key] = adapter
	return adapters


def get_adapter(key: str) -> ERPAdapter:
	adapter = get_adapters().get(key)
	if not adapter:
		raise AdapterError(f"No ERP adapter is registered for {key}")
	return adapter


@frappe.whitelist()
def get_available_erp_systems() -> list[dict]:
	"""Registered adapters with their availability, for pickers in the UI."""
	return [
		{"key": adapter.key, "label": adapter.label, "available": adapter.is_available()}
		for adapter in get_adapters().values()
	]
