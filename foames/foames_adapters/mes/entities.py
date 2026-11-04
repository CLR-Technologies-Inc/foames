# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""How a kernel reference type maps to a resource of an MES, and how one record of it is found.

A resource is addressed by a path relative to the connection's base URL, which may carry `{site}`
(the connection's plant, site or tenant id) and, for a lookup by path, `{<key field>}` where the key
goes. One record is found in one of four ways:

- **Path**: `GET <path>` with the key in the path (`parts/{id}`, or appended when the path has no
  placeholder).
- **Query**: `GET <path>?<key field>=<value>`, the plain query-parameter filter most REST APIs use.
- **OData**: `GET <path>?$filter=<key field> eq '<value>'&$top=2`.
- **JSON Filter**: `GET <path>?filter={"<key field>":"<value>"}`.

Composite keys are written into External Reference's single `external_id` as the key values joined
by `|`, in `key_fields` order. A collection answer is unwrapped whatever its envelope, and the first
record is taken; a label is read from a dotted path into the record.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field

from foames.foames_adapters.mes.rest import json_filter, odata_literal

KEY_SEPARATOR = "|"
BY_PATH = "Path"
BY_QUERY = "Query"
BY_ODATA = "OData"
BY_JSON = "JSON Filter"
LOOKUPS = (BY_PATH, BY_QUERY, BY_ODATA, BY_JSON)


@dataclass
class EntitySpec:
	path: str  # relative to the base URL; may carry {site} and, for Path lookups, {<key field>}
	key_fields: tuple[str, ...]
	lookup: str = BY_QUERY
	label_field: str = ""  # dotted path into the record
	extra_query: dict = field(default_factory=dict)  # fixed query parameters, values may carry {site}

	def keys_for(self, external_id: str) -> dict:
		parts = (external_id or "").split(KEY_SEPARATOR)
		if len(parts) != len(self.key_fields) or not all(part.strip() for part in parts):
			raise ValueError(
				f"{external_id!r} does not match the key {KEY_SEPARATOR.join(self.key_fields)} of {self.path}"
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

	def request(self, keys: dict) -> tuple[str, dict, bool]:
		"""`(path, query, single)` for the lookup of one record: `single` says the answer is the
		record itself rather than a collection."""
		query = dict(self.extra_query)
		if self.lookup == BY_PATH:
			path = self.path
			for name, value in keys.items():
				placeholder = "{" + name + "}"
				quoted = urllib.parse.quote(str(value), safe="")
				path = (
					path.replace(placeholder, quoted)
					if placeholder in path
					else path.rstrip("/") + "/" + quoted
				)
			return path, query, True
		if self.lookup == BY_QUERY:
			query.update(keys)
			return self.path, query, False
		if self.lookup == BY_ODATA:
			query["$filter"] = " and ".join(
				f"{name} eq {odata_literal(value)}" for name, value in keys.items()
			)
			query["$top"] = "2"
			return self.path, query, False
		if self.lookup == BY_JSON:
			query["filter"] = json_filter(keys)
			return self.path, query, False
		raise ValueError(f"Unknown lookup {self.lookup!r}")


def value_at(data, path: str):
	"""The value at a dotted path such as `material.description`; None when any step is missing."""
	current = data
	for step in path.split("."):
		if isinstance(current, dict):
			current = current.get(step)
		elif isinstance(current, list) and step.isdigit() and int(step) < len(current):
			current = current[int(step)]
		else:
			return None
	return current


def parse_query(text: str) -> dict:
	"""`a=b&c={site}` into a dict, for the extra query of a mapping row."""
	out = {}
	for pair in (text or "").replace("\n", "&").split("&"):
		pair = pair.strip()
		if not pair:
			continue
		name, _, value = pair.partition("=")
		if not name.strip():
			raise ValueError(f"{pair!r} is not a name=value pair")
		out[name.strip()] = value.strip()
	return out


def spec_from_override(row: dict) -> EntitySpec:
	"""Build a spec from an MES Entity Mapping row: path, lookup, key_fields as a comma list,
	label_field, extra_query as `name=value` pairs."""
	keys = tuple(name.strip() for name in (row.get("key_fields") or "").split(",") if name.strip())
	if not (row.get("path") or "").strip() or not keys:
		raise ValueError("An entity mapping needs a path and at least one key field")
	lookup = (row.get("lookup") or BY_QUERY).strip()
	if lookup not in LOOKUPS:
		raise ValueError(f"Lookup must be one of {', '.join(LOOKUPS)}, not {lookup!r}")
	return EntitySpec(
		path=row["path"].strip(),
		key_fields=keys,
		lookup=lookup,
		label_field=(row.get("label_field") or "").strip(),
		extra_query=parse_query(row.get("extra_query") or ""),
	)
