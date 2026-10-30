# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Which S/4HANA OData entity each kernel reference type resolves to.

Only reference types with a well-known released API get a default. The others (Unit of Measure,
Operation, Location, Serial Number) differ between releases and editions, so a site maps them in
S4HANA Settings after checking the system's $metadata. A site can also override any default.

Composite keys are written into External Reference's single `external_id` as the key values joined
by `|`, in `key_fields` order. Keys with a default may be left out: a Batch without a plant is
`MATERIAL|BATCH` (batch unique at material level) and with one `MATERIAL|PLANT|BATCH`.
"""

from dataclasses import dataclass, field

KEY_SEPARATOR = "|"


@dataclass
class EntitySpec:
	service: str
	entity_set: str
	key_fields: tuple[str, ...]
	label_field: str = ""
	# Keys that may be left out of external_id, with the value used then.
	key_defaults: dict = field(default_factory=dict)
	# Navigation to a language-dependent text: (navigation property, language field, text field).
	label_text: tuple[str, str, str] | None = None

	def keys_for(self, external_id: str) -> dict:
		parts = external_id.split(KEY_SEPARATOR)
		if len(parts) == len(self.key_fields):
			return dict(zip(self.key_fields, parts, strict=True))
		required = [name for name in self.key_fields if name not in self.key_defaults]
		if len(parts) != len(required):
			raise ValueError(
				f"{external_id!r} does not match the key {KEY_SEPARATOR.join(self.key_fields)} of {self.entity_set}"
			)
		values = dict(zip(required, parts, strict=True))
		return {name: values.get(name, self.key_defaults.get(name)) for name in self.key_fields}

	def external_id_for(self, entity: dict) -> str:
		values = [str(entity.get(name) or "") for name in self.key_fields]
		required = [name for name in self.key_fields if name not in self.key_defaults]
		if len(required) < len(self.key_fields) and all(
			entity.get(name, default) == default for name, default in self.key_defaults.items()
		):
			values = [str(entity.get(name) or "") for name in required]
		return KEY_SEPARATOR.join(values)

	def query(self) -> dict:
		if self.label_text:
			return {"$expand": self.label_text[0]}
		return {}

	def label_for(self, entity: dict, language: str = "EN") -> str:
		if self.label_text:
			navigation, language_field, text_field = self.label_text
			texts = (entity.get(navigation) or {}).get("results", [])
			for text in texts:
				if str(text.get(language_field, "")).upper() == language.upper() and text.get(text_field):
					return text[text_field]
			for text in texts:
				if text.get(text_field):
					return text[text_field]
		if self.label_field and entity.get(self.label_field):
			return str(entity[self.label_field])
		return self.external_id_for(entity)


# Defaults from SAP's released on-premise APIs. Check them against the system's $metadata: entity
# sets and key fields can differ by release, and each service needs a communication arrangement.
DEFAULT_ENTITIES: dict[str, EntitySpec] = {
	"Item": EntitySpec(
		service="API_PRODUCT_SRV",
		entity_set="A_Product",
		key_fields=("Product",),
		label_text=("to_Description", "Language", "ProductDescription"),
	),
	"Batch": EntitySpec(
		service="API_BATCH_SRV",
		entity_set="Batch",
		key_fields=("Material", "BatchIdentifyingPlant", "Batch"),
		key_defaults={"BatchIdentifyingPlant": ""},
		label_field="Batch",
	),
	"Work Order": EntitySpec(
		service="API_PRODUCTION_ORDER_2_SRV",
		entity_set="A_ProductionOrder_2",
		key_fields=("ManufacturingOrder",),
		label_field="Material",
	),
	"Stock Movement": EntitySpec(
		service="API_MATERIAL_DOCUMENT_SRV",
		entity_set="A_MaterialDocumentHeader",
		key_fields=("MaterialDocumentYear", "MaterialDocument"),
		label_field="MaterialDocumentHeaderText",
	),
}


def spec_from_override(row: dict) -> EntitySpec:
	"""Build a spec from an S4HANA Entity Mapping row (service, entity_set, key_fields as a comma
	list, label_field, optional_keys as a comma list of keys that default to an empty string)."""
	keys = tuple(name.strip() for name in (row.get("key_fields") or "").split(",") if name.strip())
	if not row.get("service") or not row.get("entity_set") or not keys:
		raise ValueError("An entity mapping needs a service, an entity set and at least one key field")
	optional = [name.strip() for name in (row.get("optional_keys") or "").split(",") if name.strip()]
	return EntitySpec(
		service=row["service"].strip(),
		entity_set=row["entity_set"].strip(),
		key_fields=keys,
		label_field=(row.get("label_field") or "").strip(),
		key_defaults={name: "" for name in optional if name in keys},
	)
