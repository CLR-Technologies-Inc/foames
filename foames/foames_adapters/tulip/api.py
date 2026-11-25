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

"""Tulip's public read API: paths and query parameters, with no Frappe import.

Written from Tulip's public API documentation on support.tulip.co (the Table API guide, the apidocs
pages for tables, records, machines and stations, checked 2026-11-15). What it covers:

- **Tables** (scope `tables:read`): `GET tables` (limit 1..100, offset, includeDeleted);
  `GET tables/{tableId}/records` (limit 1..100, default 10; offset; includeTotalCount; `filters`,
  a JSON list of `{"field", "functionType", "arg"}`; `filterAggregator` all or any; `fields`, a JSON
  list of column names; `sortOptions`, a JSON list of `{"sortBy", "sortDir"}`);
  `GET tables/{tableId}/count` (filters, filterAggregator); `GET tables/{tableId}/records/{recordId}`.
  The Table API lives under `api/v3`, with `w/{workspace}/` after it when the instance uses
  workspaces (a global service account must name the workspace).
- **Machines** (scope `machines:read`): `GET machines`, the machine types and their machines.
- **Stations** (scope `stations:read`): `GET api/stations/v1/stations` (limit, offset, sort, search,
  archived, and an OData `filter` on stationGroupId only).

Everything here reads. A write to Tulip (creating a table record with `tables:write`, reporting
machine attributes with `attributes:report`) is an MES Outbox posting through the REST Request
operation, which the write gate holds for sign-off while the Tulip connector is read-only. Give the
service account read scopes only until the plant approves its writes.
"""

from __future__ import annotations

import json
import re
import urllib.parse

API = "api/v3"
STATIONS_API = "api/stations/v1"
MAX_LIMIT = 100
TABLE_ID = re.compile(r"^[a-zA-Z0-9_]+$")
FUNCTION_TYPES = (
	"equal",
	"notEqual",
	"blank",
	"notBlank",
	"greaterThan",
	"greaterThanOrEqual",
	"lessThan",
	"lessThanOrEqual",
	"isIn",
	"notIsIn",
	"contains",
	"notContains",
	"startsWith",
	"notStartsWith",
	"endsWith",
	"notEndsWith",
)
# Functions that take no argument.
NO_ARG = ("blank", "notBlank")
AGGREGATORS = ("all", "any")
SORT_DIRECTIONS = ("asc", "desc")
STATION_SORTS = ("name", "-name", "lastModified.at", "-lastModified.at", "created.at", "-created.at")
# Tulip's own fields, which can be filtered and sorted on besides the table's columns.
SYSTEM_FIELDS = ("id", "_createdAt", "_updatedAt", "_sequenceNumber")


def _workspace(workspace: str | None) -> str:
	workspace = (workspace or "").strip()
	return f"w/{urllib.parse.quote(workspace, safe='')}/" if workspace else ""


def table_id(value: str) -> str:
	value = (value or "").strip()
	if not TABLE_ID.match(value):
		raise ValueError(f"{value!r} is not a Tulip table id (letters, digits and underscores)")
	return value


def tables_path(workspace: str | None = None) -> str:
	return f"{API}/{_workspace(workspace)}tables"


def records_path(table: str, workspace: str | None = None, record: str | None = None) -> str:
	path = f"{tables_path(workspace)}/{table_id(table)}/records"
	if record is not None:
		record = str(record)
		if not record.strip():
			raise ValueError("A record id cannot be empty")
		path += "/" + urllib.parse.quote(record, safe="")
	return path


def count_path(table: str, workspace: str | None = None) -> str:
	return f"{tables_path(workspace)}/{table_id(table)}/count"


def machines_path(workspace: str | None = None) -> str:
	return f"{API}/{_workspace(workspace)}machines"


def stations_path(workspace: str | None = None) -> str:
	return f"{STATIONS_API}/{_workspace(workspace)}stations"


def limit_of(limit, maximum: int = MAX_LIMIT, default: int = MAX_LIMIT) -> int:
	if limit in (None, ""):
		return default
	limit = int(limit)
	if limit < 1:
		raise ValueError("limit must be at least 1")
	return min(limit, maximum)


def offset_of(offset) -> int:
	offset = int(offset or 0)
	if offset < 0:
		raise ValueError("offset cannot be negative")
	return offset


def check_filters(filters) -> list[dict]:
	"""Filters as Tulip takes them: a list of {"field", "functionType", "arg"}. A dict
	{"field": value} is read as equal filters, for convenience."""
	if filters in (None, "", [], {}):
		return []
	if isinstance(filters, str):
		filters = json.loads(filters)
	if isinstance(filters, dict):
		filters = [{"field": k, "functionType": "equal", "arg": v} for k, v in filters.items()]
	if not isinstance(filters, list):
		raise ValueError("filters must be a list of {field, functionType, arg}")
	out = []
	for item in filters:
		if not isinstance(item, dict) or not str(item.get("field") or "").strip():
			raise ValueError("Each filter needs a field")
		function = item.get("functionType") or "equal"
		if function not in FUNCTION_TYPES:
			raise ValueError(f"{function!r} is not a Tulip filter function")
		row = {"field": str(item["field"]), "functionType": function}
		if function not in NO_ARG:
			if "arg" not in item:
				raise ValueError(f"The filter on {item['field']} needs an arg")
			if function in ("isIn", "notIsIn") and not isinstance(item["arg"], list):
				raise ValueError(f"{function} needs a list arg")
			row["arg"] = item["arg"]
		out.append(row)
	return out


def check_sort(sort) -> list[dict]:
	if sort in (None, "", []):
		return []
	if isinstance(sort, str):
		sort = json.loads(sort)
	out = []
	for item in sort if isinstance(sort, list) else [sort]:
		if not isinstance(item, dict) or not item.get("sortBy"):
			raise ValueError("Each sort option needs sortBy")
		direction = item.get("sortDir") or "asc"
		if direction not in SORT_DIRECTIONS:
			raise ValueError("sortDir is asc or desc")
		out.append({"sortBy": str(item["sortBy"]), "sortDir": direction})
	return out


def _json(value) -> str:
	return json.dumps(value, separators=(",", ":"))


def records_query(
	*,
	limit=None,
	offset=None,
	filters=None,
	filter_aggregator: str | None = None,
	fields=None,
	sort=None,
	include_total_count: bool = False,
) -> dict:
	"""The query string of a records list."""
	query = {"limit": limit_of(limit), "offset": offset_of(offset)}
	checked = check_filters(filters)
	if checked:
		query["filters"] = _json(checked)
	if filter_aggregator:
		if filter_aggregator not in AGGREGATORS:
			raise ValueError("filterAggregator is all or any")
		query["filterAggregator"] = filter_aggregator
	if fields:
		if isinstance(fields, str):
			fields = (
				json.loads(fields)
				if fields.strip().startswith("[")
				else [f.strip() for f in fields.split(",")]
			)
		query["fields"] = _json([str(f) for f in fields if str(f).strip()])
	sorted_by = check_sort(sort)
	if sorted_by:
		query["sortOptions"] = _json(sorted_by)
	if include_total_count:
		query["includeTotalCount"] = "true"
	return query


def count_query(*, filters=None, filter_aggregator: str | None = None) -> dict:
	query = {}
	checked = check_filters(filters)
	if checked:
		query["filters"] = _json(checked)
	if filter_aggregator:
		if filter_aggregator not in AGGREGATORS:
			raise ValueError("filterAggregator is all or any")
		query["filterAggregator"] = filter_aggregator
	return query


def tables_query(*, limit=None, offset=None, include_deleted: bool = False) -> dict:
	query = {"limit": limit_of(limit), "offset": offset_of(offset)}
	if include_deleted:
		query["includeDeleted"] = "true"
	return query


def stations_query(
	*,
	limit=None,
	offset=None,
	search: str | None = None,
	sort: str | None = None,
	archived: bool = False,
	station_group: str | None = None,
) -> dict:
	query = {"limit": limit_of(limit), "offset": offset_of(offset)}
	if search:
		query["search"] = search
	if sort:
		for part in sort.split(","):
			if part.strip() not in STATION_SORTS:
				raise ValueError(f"{part!r} is not a station sort ({', '.join(STATION_SORTS)})")
		query["sort"] = sort
	if archived:
		query["archived"] = "true"
	if station_group:
		query["filter"] = "stationGroupId eq '" + str(station_group).replace("'", "''") + "'"
	return query


def flatten_machines(answer) -> list[dict]:
	"""`GET machines` answers machine types, each with its machines; one row per machine."""
	rows = []
	for machine_type in answer if isinstance(answer, list) else []:
		if not isinstance(machine_type, dict):
			continue
		for machine in machine_type.get("machines") or []:
			if isinstance(machine, dict):
				rows.append(
					{
						"id": machine.get("id"),
						"name": machine.get("name"),
						"machine_type_id": machine_type.get("id"),
						"machine_type": machine_type.get("name"),
					}
				)
	return rows


def table_summary(table: dict) -> dict:
	"""A table's id, label and columns, without the rest of the answer."""
	return {
		"id": table.get("id"),
		"label": table.get("label"),
		"description": table.get("description"),
		"columns": [
			{
				"name": column.get("name"),
				"label": column.get("label"),
				"type": (column.get("dataType") or {}).get("type"),
				"unique": column.get("unique"),
				"hidden": column.get("hidden"),
			}
			for column in table.get("columns") or []
			if isinstance(column, dict)
		],
	}
