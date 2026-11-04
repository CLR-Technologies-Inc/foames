# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The adapter class every vendor folder subclasses with its profile.

Each registered adapter reads one **MES Connection** record named after its key. Without that
record, or with it disabled, the adapter is registered but unavailable: External References can be
created for it and resolve later, exactly like a remote ERP that is down.
"""

from __future__ import annotations

from foames.foames_adapters.base import AdapterError, AdapterUnavailable, ERPAdapter, ResolvedReference
from foames.foames_adapters.mes.entities import EntitySpec, spec_from_override
from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import MESError, items_of

CONNECTION = "MES Connection"


class ProfileAdapter(ERPAdapter):
	profile: Profile

	def __init__(self, connection=None, transport=None):
		# Both are for tests; on a site the connection is read from MES Connection.
		self._connection = connection
		self._transport = transport
		self.key = self.profile.key
		self.label = self.profile.label

	@property
	def connection(self):
		"""The MES Connection document for this adapter, or None when the site has none."""
		if self._connection is not None:
			return self._connection
		import frappe

		if not frappe.db.exists(CONNECTION, self.profile.key):
			return None
		return frappe.get_cached_doc(CONNECTION, self.profile.key)

	def entity_specs(self) -> dict[str, EntitySpec]:
		specs = dict(self.profile.entities)
		connection = self.connection
		for row in getattr(connection, "entity_mappings", None) or []:
			row = row if isinstance(row, dict) else row.as_dict()
			specs[row["reference_type"]] = spec_from_override(row)
		return specs

	@property
	def reference_map(self) -> dict[str, str]:
		return {reference_type: spec.path for reference_type, spec in self.entity_specs().items()}

	def is_available(self) -> bool:
		connection = self.connection
		return bool(connection and connection.enabled and connection.base_url)

	def client(self):
		return self.connection.client(self._transport)

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		spec = self.entity_specs()[reference_type]
		try:
			keys = spec.keys_for(external_id)
		except ValueError:
			# An ID that cannot be a key of this resource cannot exist in the system.
			return None
		entity = self.lookup(spec, keys)
		if not entity:
			return None
		return ResolvedReference(
			reference_type=reference_type,
			external_id=spec.external_id_for(entity) or external_id,
			label=spec.label_for(entity),
			data={"path": spec.path, "lookup": spec.lookup, "keys": keys},
		)

	def lookup(self, spec: EntitySpec, keys: dict) -> dict | None:
		path, query, single = spec.request(keys)
		try:
			data = self.client().get(path, query)
		except MESError as e:
			raise self.adapter_error(e)
		if single:
			if data is None:
				return None
			return data if isinstance(data, dict) and data else None
		if data is None:
			# A collection that does not exist is a wrong path on the mapping, not a missing record.
			raise AdapterError(f"{self.label}: no collection at {path}; check the mapping's path")
		records = items_of(data)
		return records[0] if records and isinstance(records[0], dict) else None

	def adapter_error(self, error: MESError) -> AdapterError:
		if error.transient:
			return AdapterUnavailable(f"{self.label}: {error}")
		return AdapterError(f"{self.label}: {error}")
