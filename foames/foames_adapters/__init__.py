# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

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
