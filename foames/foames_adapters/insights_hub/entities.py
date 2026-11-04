# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Which Insights Hub resource each kernel reference type resolves to.

Only the platform's own asset model gets defaults: a Workstation and a Location are Insights Hub
assets (Asset Management v3), which is what Opcenter Intelligence models equipment and the plant
hierarchy on. Materials, orders, operations, batches and the other production records live in
Opcenter Intelligence's own resources, whose paths and fields a site takes from the Opcenter
Intelligence API reference and enters in Insights Hub Settings. A site can also override a default.

A resource is found either by path (`<service>/<resource>/<id>`, for a resource addressed by its id)
or by filter (`<service>/<resource>?filter={"<key>":"<value>"}`, for one addressed by another field
such as an external id or a number). Composite keys are written into External Reference's single
`external_id` as the key values joined by `|`, in `key_fields` order.
"""

from __future__ import annotations

from dataclasses import dataclass

KEY_SEPARATOR = "|"
BY_PATH = "Path"
BY_FILTER = "Filter"

ASSET_MANAGEMENT = "assetmanagement/v3"


@dataclass
class EntitySpec:
	service: str  # the API behind the gateway, with its version: assetmanagement/v3
	resource: str  # the collection inside it: assets
	key_fields: tuple[str, ...]  # field names whose values make up the external id
	lookup: str = BY_PATH  # Path: GET <resource>/<id>; Filter: GET <resource>?filter={...}
	label_field: str = ""  # dotted path to the text shown for the record; falls back to the id

	def path(self) -> str:
		return self.service.strip("/") + "/" + self.resource.strip("/")

	def keys_for(self, external_id: str) -> dict:
		parts = [part for part in (external_id or "").split(KEY_SEPARATOR)]
		if len(parts) != len(self.key_fields) or not all(part.strip() for part in parts):
			raise ValueError(
				f"{external_id!r} does not match the key {KEY_SEPARATOR.join(self.key_fields)} of {self.resource}"
			)
		return dict(zip(self.key_fields, (part.strip() for part in parts), strict=True))

	def external_id_for(self, entity: dict) -> str:
		return KEY_SEPARATOR.join(str(value_at(entity, name) or "") for name in self.key_fields)

	def label_for(self, entity: dict) -> str:
		if self.label_field:
			value = value_at(entity, self.label_field)
			if value not in (None, ""):
				return str(value)
		return self.external_id_for(entity)


def value_at(data, path: str):
	"""The value at a dotted path such as `location.locality`; None when any step is missing."""
	current = data
	for step in path.split("."):
		if isinstance(current, dict):
			current = current.get(step)
		elif isinstance(current, list) and step.isdigit() and int(step) < len(current):
			current = current[int(step)]
		else:
			return None
	return current


# Insights Hub Asset Management is the one API every tenant has, and the one Opcenter Intelligence
# models equipment and the plant structure on. The resource keys below are the platform's own.
DEFAULT_ENTITIES: dict[str, EntitySpec] = {
	# Equipment: an asset, addressed by its asset id.
	"Workstation": EntitySpec(
		service=ASSET_MANAGEMENT, resource="assets", key_fields=("assetId",), label_field="name"
	),
	# A plant, area or line: also an asset, one higher up the hierarchy.
	"Location": EntitySpec(
		service=ASSET_MANAGEMENT, resource="assets", key_fields=("assetId",), label_field="name"
	),
}


def spec_from_override(row: dict) -> EntitySpec:
	"""Build a spec from an Insights Hub Entity Mapping row: service, resource, key_fields as a
	comma list, lookup (Path or Filter) and label_field."""
	keys = tuple(name.strip() for name in (row.get("key_fields") or "").split(",") if name.strip())
	if not row.get("service") or not row.get("resource") or not keys:
		raise ValueError("An entity mapping needs a service, a resource and at least one key field")
	lookup = (row.get("lookup") or BY_PATH).strip()
	if lookup not in (BY_PATH, BY_FILTER):
		raise ValueError(f"Lookup must be {BY_PATH} or {BY_FILTER}, not {lookup!r}")
	if lookup == BY_PATH and len(keys) != 1:
		raise ValueError(
			"A resource looked up by path has exactly one key field; use Filter for a composite key"
		)
	return EntitySpec(
		service=row["service"].strip(),
		resource=row["resource"].strip(),
		key_fields=keys,
		lookup=lookup,
		label_field=(row.get("label_field") or "").strip(),
	)
