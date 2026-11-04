# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Insights Hub adapter registered through the `foames_erp_adapters` hook.

A Workstation or a Location resolves to an Insights Hub asset by default; the Opcenter Intelligence
resources a site maps in Insights Hub Settings resolve against their paths. A Job Card is the job a
machine works on, written `ORDER|OPERATION`: when the site maps Work Order, the order is checked
there and the job carries the order's label; otherwise the job is accepted as the tag the roll-up
writes into the machine's time series, which is all Opcenter Intelligence needs of it.
"""

from __future__ import annotations

import urllib.parse

from foames.foames_adapters.base import AdapterError, AdapterUnavailable, ERPAdapter, ResolvedReference
from foames.foames_adapters.insights_hub import ADAPTER_KEY
from foames.foames_adapters.insights_hub.entities import BY_PATH, KEY_SEPARATOR, EntitySpec
from foames.foames_adapters.insights_hub.rest import InsightsHubError, json_filter

JOB_CARD = "Job Card"
WORK_ORDER = "Work Order"


def parse_job(external_id: str) -> tuple[str, str]:
	"""`(order, operation)` out of `ORDER|OPERATION`; the operation may be left out (`ORDER`)."""
	parts = [part.strip() for part in (external_id or "").split(KEY_SEPARATOR)]
	if len(parts) not in (1, 2) or not parts[0]:
		raise ValueError(
			f"{external_id!r} is not a job; write it as ORDER or ORDER{KEY_SEPARATOR}OPERATION, "
			f"for example 1000123{KEY_SEPARATOR}0010"
		)
	return parts[0], parts[1] if len(parts) == 2 else ""


def job_id(order: str, operation: str = "") -> str:
	return f"{order}{KEY_SEPARATOR}{operation}" if operation else order


class InsightsHubAdapter(ERPAdapter):
	key = ADAPTER_KEY
	label = "Siemens Insights Hub"

	def __init__(self, settings=None, transport=None):
		# Both are for tests; on a site the settings are read from Insights Hub Settings.
		self._settings = settings
		self._transport = transport

	@property
	def settings(self):
		if self._settings is not None:
			return self._settings
		from foames.foames_adapters.doctype.insights_hub_settings.insights_hub_settings import get_settings

		return get_settings()

	@property
	def reference_map(self) -> dict[str, str]:
		mapped = {
			reference_type: spec.resource for reference_type, spec in self.settings.entity_specs().items()
		}
		mapped.setdefault(JOB_CARD, "Job")
		return mapped

	def is_available(self) -> bool:
		settings = self.settings
		return bool(settings.enabled and settings.gateway_url)

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		specs = self.settings.entity_specs()
		if reference_type == JOB_CARD and JOB_CARD not in specs:
			return self.fetch_job(external_id, specs)
		spec = specs[reference_type]
		try:
			keys = spec.keys_for(external_id)
		except ValueError:
			# An ID that cannot be a key of this resource cannot exist in Insights Hub.
			return None
		entity = self.lookup(spec, keys)
		if not entity:
			return None
		return ResolvedReference(
			reference_type=reference_type,
			external_id=spec.external_id_for(entity) or external_id,
			label=spec.label_for(entity),
			data={"service": spec.service, "resource": spec.resource, "keys": keys},
		)

	def lookup(self, spec: EntitySpec, keys: dict) -> dict | None:
		client = self.settings.client(self._transport)
		try:
			if spec.lookup == BY_PATH:
				value = next(iter(keys.values()))
				found = client.get(spec.path() + "/" + urllib.parse.quote(str(value), safe=""))
				return found if isinstance(found, dict) else None
			found = client.get_page(spec.path(), {"filter": json_filter(keys)}, size=2)
			return found[0] if found and isinstance(found[0], dict) else None
		except InsightsHubError as e:
			raise self.adapter_error(e)

	def fetch_job(self, external_id: str, specs: dict[str, EntitySpec]) -> ResolvedReference | None:
		"""A job (`ORDER|OPERATION`) as a Job Card, checked against the Work Order mapping when the
		site has one."""
		try:
			order, operation = parse_job(external_id)
		except ValueError:
			return None
		data = {"order": order, "operation": operation, "checked": False}
		label = f"{order} {operation}".strip()
		if WORK_ORDER in specs:
			spec = specs[WORK_ORDER]
			try:
				keys = spec.keys_for(order)
			except ValueError:
				return None
			found = self.lookup(spec, keys)
			if not found:
				return None
			order = spec.external_id_for(found) or order
			data.update({"order": order, "checked": True, "order_label": spec.label_for(found)})
			label = f"{order} {operation}: {spec.label_for(found)}".replace("  ", " ")
		return ResolvedReference(
			reference_type=JOB_CARD, external_id=job_id(order, operation), label=label, data=data
		)

	def adapter_error(self, error: InsightsHubError) -> AdapterError:
		if error.transient:
			return AdapterUnavailable(f"{self.label}: {error}")
		return AdapterError(f"{self.label}: {error}")
