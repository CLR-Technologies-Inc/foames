# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The S/4HANA adapter registered through the `foames_erp_adapters` hook."""

from foames.foames_adapters.base import AdapterError, AdapterUnavailable, ERPAdapter, ResolvedReference
from foames.foames_adapters.s4hana.odata import ODataError

ADAPTER_KEY = "S4HANA"


class S4HANAAdapter(ERPAdapter):
	key = ADAPTER_KEY
	label = "SAP S/4HANA"

	def __init__(self, settings=None, transport=None):
		# Both are for tests; on a site the settings are read from S4HANA Settings.
		self._settings = settings
		self._transport = transport

	@property
	def settings(self):
		if self._settings is not None:
			return self._settings
		from foames.foames_adapters.doctype.s4hana_settings.s4hana_settings import get_settings

		return get_settings()

	@property
	def reference_map(self) -> dict[str, str]:
		return {
			reference_type: spec.entity_set for reference_type, spec in self.settings.entity_specs().items()
		}

	def is_available(self) -> bool:
		settings = self.settings
		return bool(settings.enabled and settings.base_url)

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		settings = self.settings
		spec = settings.entity_specs()[reference_type]
		try:
			keys = spec.keys_for(external_id)
		except ValueError:
			# An ID that cannot be a key of this entity cannot exist in S/4HANA.
			return None
		try:
			entity = settings.client(self._transport).get_entity(
				spec.service, spec.entity_set, keys, spec.query()
			)
		except ODataError as e:
			if e.transient or e.status in (401, 403):
				raise AdapterUnavailable(f"{self.label}: {e}")
			raise AdapterError(f"{self.label}: {e}")
		if not entity:
			return None
		return ResolvedReference(
			reference_type=reference_type,
			external_id=spec.external_id_for(entity) or external_id,
			label=spec.label_for(entity, settings.language or "EN"),
			data={"service": spec.service, "entity_set": spec.entity_set, "keys": keys},
		)
