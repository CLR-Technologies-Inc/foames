# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read Tulip through its public API: tables and their records, machines, stations.

These methods only read, so they run whatever the connector's read-only mode says. They use the
site's Tulip MES Connection (key TULIP): its Base URL, its service account key and secret as Basic
authentication, and its Site field as the Tulip workspace id (leave it empty when the instance has
no workspaces or the service account belongs to one). Writes to Tulip are MES Outbox postings and
pass the write gate. The paths and parameters are in `api.py`.
"""

from __future__ import annotations

import frappe
from frappe import _

from foames.foames_adapters.mes.rest import MESError
from foames.foames_adapters.tulip import ADAPTER_KEY
from foames.foames_adapters.tulip import api as tulip

CONNECTION = "MES Connection"


def _client():
	frappe.has_permission(CONNECTION, "read", throw=True)
	if not frappe.db.exists(CONNECTION, ADAPTER_KEY):
		frappe.throw(_("Create an MES Connection for {0} first").format(ADAPTER_KEY))
	connection = frappe.get_doc(CONNECTION, ADAPTER_KEY)
	if not connection.enabled or not connection.base_url:
		frappe.throw(_("The {0} MES Connection is disabled or has no Base URL").format(ADAPTER_KEY))
	return connection.client(), (connection.site or "").strip()


def _get(path: str, query: dict | None = None):
	client, _workspace = _client()
	try:
		return client.get(path, query)
	except MESError as e:
		frappe.throw(_("Tulip answered: {0}").format(str(e)))
	except ValueError as e:
		frappe.throw(str(e))


def _workspace() -> str:
	return _client()[1]


def _checked(fn, *args, **kwargs):
	try:
		return fn(*args, **kwargs)
	except (ValueError, TypeError) as e:
		frappe.throw(str(e))


@frappe.whitelist()
def list_tables(limit: int = 100, offset: int = 0, include_deleted: bool = False) -> list[dict]:
	"""The workspace's Tulip Tables with their columns."""
	query = _checked(tulip.tables_query, limit=limit, offset=offset, include_deleted=bool(include_deleted))
	answer = _get(tulip.tables_path(_workspace()), query) or []
	return [tulip.table_summary(table) for table in answer if isinstance(table, dict)]


@frappe.whitelist()
def list_table_records(
	table: str,
	filters: str | list | dict | None = None,
	filter_aggregator: str | None = None,
	fields: str | list | None = None,
	sort: str | list | None = None,
	limit: int = 100,
	offset: int = 0,
) -> list[dict]:
	"""Records of one Tulip Table, at most 100 a call; page with offset."""
	path = _checked(tulip.records_path, table, _workspace())
	query = _checked(
		tulip.records_query,
		limit=limit,
		offset=offset,
		filters=filters,
		filter_aggregator=filter_aggregator,
		fields=fields,
		sort=sort,
	)
	return _get(path, query) or []


@frappe.whitelist()
def count_table_records(
	table: str, filters: str | list | dict | None = None, filter_aggregator: str | None = None
) -> int:
	path = _checked(tulip.count_path, table, _workspace())
	query = _checked(tulip.count_query, filters=filters, filter_aggregator=filter_aggregator)
	return int(_get(path, query) or 0)


@frappe.whitelist()
def get_table_record(table: str, record: str) -> dict | None:
	path = _checked(tulip.records_path, table, _workspace(), record)
	return _get(path)


@frappe.whitelist()
def list_machines() -> list[dict]:
	"""Tulip machines, one row each, with their machine type."""
	return tulip.flatten_machines(_get(tulip.machines_path(_workspace())))


@frappe.whitelist()
def list_stations(
	search: str | None = None,
	station_group: str | None = None,
	archived: bool = False,
	sort: str | None = None,
	limit: int = 100,
	offset: int = 0,
) -> list[dict]:
	"""Tulip stations: where apps run, with the station group, operator and app state."""
	query = _checked(
		tulip.stations_query,
		limit=limit,
		offset=offset,
		search=search,
		sort=sort,
		archived=bool(archived),
		station_group=station_group,
	)
	answer = _get(tulip.stations_path(_workspace()), query) or {}
	return answer.get("items", []) if isinstance(answer, dict) else answer


def mcp_tools():
	"""The Tulip read tools for the MCP server (registered with the `foames_mcp_tools` hook)."""
	from foames.foames_mcp.protocol import Tool

	base = "foames.foames_adapters.tulip.reads"

	def s(description, **extra):
		return {"type": "string", "description": description, **extra}

	def i(description, **extra):
		return {"type": "integer", "description": description, **extra}

	def schema(properties, required=None):
		out = {"type": "object", "properties": properties, "additionalProperties": False}
		if required:
			out["required"] = required
		return out

	limit = i("Rows to return (at most 100)", minimum=1, maximum=100)
	offset = i("Rows to skip, for paging", minimum=0)
	filters = {
		"type": "array",
		"description": 'Tulip filters: [{"field": "<column>", "functionType": "equal", "arg": "<value>"}]; functionType is one of '
		+ ", ".join(tulip.FUNCTION_TYPES),
		"items": {"type": "object", "additionalProperties": True},
	}
	aggregator = s("How filters combine (default all)", enum=list(tulip.AGGREGATORS))
	table = s("Tulip table id")
	return [
		Tool(
			name="foames_tulip_list_tables",
			title="List Tulip tables",
			description="Tulip Tables in the connected workspace with their columns (name, label, type). Reads only. Needs read on MES Connection and a Tulip service account with tables:read.",
			method=f"{base}.list_tables",
			input_schema=schema({"limit": limit, "offset": offset}),
		),
		Tool(
			name="foames_tulip_list_table_records",
			title="List Tulip table records",
			description="Records of one Tulip Table (orders, units, batches, whatever the site keeps there), filtered and sorted, at most 100 a call. Reads only. Needs tables:read.",
			method=f"{base}.list_table_records",
			input_schema=schema(
				{
					"table": table,
					"filters": filters,
					"filter_aggregator": aggregator,
					"fields": {
						"type": "array",
						"items": {"type": "string"},
						"description": "Columns to return",
					},
					"sort": {
						"type": "array",
						"items": {"type": "object", "additionalProperties": True},
						"description": 'Sort options: [{"sortBy": "<column>", "sortDir": "asc"}]',
					},
					"limit": limit,
					"offset": offset,
				},
				["table"],
			),
		),
		Tool(
			name="foames_tulip_count_table_records",
			title="Count Tulip table records",
			description="How many records of a Tulip Table match the filters (exact below 50,000 records). Reads only. Needs tables:read.",
			method=f"{base}.count_table_records",
			input_schema=schema(
				{"table": table, "filters": filters, "filter_aggregator": aggregator}, ["table"]
			),
		),
		Tool(
			name="foames_tulip_get_table_record",
			title="Get a Tulip table record",
			description="One record of a Tulip Table by its id. Reads only. Needs tables:read.",
			method=f"{base}.get_table_record",
			input_schema=schema({"table": table, "record": s("Record id")}, ["table", "record"]),
		),
		Tool(
			name="foames_tulip_list_machines",
			title="List Tulip machines",
			description="Tulip machines with their machine types. Reads only. Needs machines:read.",
			method=f"{base}.list_machines",
			input_schema=schema({}),
		),
		Tool(
			name="foames_tulip_list_stations",
			title="List Tulip stations",
			description="Tulip stations with their station group, operator and app state. Reads only. Needs stations:read.",
			method=f"{base}.list_stations",
			input_schema=schema(
				{
					"search": s("Part of a station name"),
					"station_group": s("Only stations of this station group id"),
					"archived": {"type": "boolean", "description": "List archived stations"},
					"sort": s("name, lastModified.at or created.at; prefix - for descending"),
					"limit": limit,
					"offset": offset,
				}
			),
		),
	]
