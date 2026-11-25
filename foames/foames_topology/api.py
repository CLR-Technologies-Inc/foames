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

"""The topology API: one graph, several read-only views of it, and an ingest for collectors.

Reads (GET or POST, any user with read access to Topology Asset; tenant-restricted users see only
their tenants and shared assets):

	get_graph        nodes, edges, layout and findings, for the Topology View page and agents
	get_mermaid      Mermaid flowchart text
	grafana          {"nodes", "edges"} for Grafana's Node Graph panel; grafana_nodes and
	                 grafana_edges return the two arrays on their own for one query each
	trace            the lineage of one asset, downstream or upstream
	overlay          data-layer health per physical asset, for a view that draws the physical layer
	                 (Floor View, a P&ID); look assets up by id or by their source record

Common filters: tenant (one, or a comma-separated list), layers ("Physical", "Data" or both) and
provider.

Writes:

	ingest           a collector report (see ingest.py); FoaMES Integration, FoaMES Engineer or
	                 System Manager
	sync_now         run the built-in sync now; FoaMES Engineer or System Manager
"""

import json

import frappe
from frappe import _

from foames.foames_topology import graph as topo
from foames.foames_topology import ingest as ingest_rules
from foames.foames_topology import model, store

WRITER_ROLES = ("System Manager", "FoaMES Engineer", "FoaMES Integration")


def _list(value):
	if value in (None, "", []):
		return None
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
		except ValueError:
			parsed = value.split(",")
		value = parsed if isinstance(parsed, list) else [parsed]
	return [str(v).strip() for v in value if str(v).strip()]


def _graph(tenant=None, layers=None, provider=None, include_disabled=0):
	frappe.has_permission("Topology Asset", "read", throw=True)
	graph = store.load_graph(include_disabled=bool(int(include_disabled or 0)))
	return topo.filter_graph(graph, tenants=_list(tenant), layers=_list(layers), providers=_list(provider))


@frappe.whitelist()
def get_graph(
	tenant: str | None = None,
	layers: str | list | None = None,
	provider: str | None = None,
	include_disabled: int | str = 0,
):
	graph = _graph(tenant, layers, provider, include_disabled)
	out = topo.graph_dict(graph)
	out["last_sync_at"] = frappe.db.get_single_value("Topology Settings", "last_sync_at")
	return out


@frappe.whitelist()
def get_mermaid(
	tenant: str | None = None,
	layers: str | list | None = None,
	provider: str | None = None,
	direction: str = "TB",
):
	if direction not in ("TB", "TD", "BT", "LR", "RL"):
		frappe.throw(_("direction must be TB, TD, BT, LR or RL"))
	return topo.to_mermaid(_graph(tenant, layers, provider), direction=direction)


@frappe.whitelist()
def grafana(tenant: str | None = None, layers: str | list | None = None, provider: str | None = None):
	return topo.to_grafana(_graph(tenant, layers, provider))


@frappe.whitelist()
def grafana_nodes(tenant: str | None = None, layers: str | list | None = None, provider: str | None = None):
	return grafana(tenant, layers, provider)["nodes"]


@frappe.whitelist()
def grafana_edges(tenant: str | None = None, layers: str | list | None = None, provider: str | None = None):
	return grafana(tenant, layers, provider)["edges"]


@frappe.whitelist()
def trace(asset: str, direction: str = "downstream", tenant: str | None = None):
	graph = _graph(tenant)
	if asset not in graph.nodes:
		frappe.throw(
			_("Topology Asset {0} is not in the graph you can see").format(asset), frappe.DoesNotExistError
		)
	try:
		return topo.trace(graph, asset, direction)
	except ValueError as e:
		frappe.throw(_(str(e)))


@frappe.whitelist()
def overlay(
	assets: str | list | None = None,
	source_doctype: str | None = None,
	source_names: str | list | None = None,
	tenant: str | None = None,
):
	"""Per physical asset: status, data health and bound signals.

	Either assets (asset ids) or source_doctype with source_names (for example "PID Component"
	and the components a P&ID drawing shows, or "Machine" and the machines on Floor View). The
	answer is keyed the same way the question was asked."""
	graph = _graph(tenant)
	if source_doctype:
		names = set(_list(source_names) or [])
		by_source = {
			n["source_name"]: n["id"]
			for n in graph.nodes.values()
			# Only the physical asset: a machine's event stream and KPI name the Machine as their
			# source too.
			if n["layer"] == model.PHYSICAL
			and n["source_doctype"] == source_doctype
			and (not names or n["source_name"] in names)
		}
		result = topo.overlay(graph, set(by_source.values()))
		return {source: result[node_id] for source, node_id in by_source.items() if node_id in result}
	ids = _list(assets)
	return topo.overlay(graph, set(ids) if ids else None)


@frappe.whitelist(methods=["POST"])
def ingest(report: dict | str | None = None, **fields):
	"""Write a collector report. Body: the report object (see ingest.py) as JSON, either as it is
	or under a "report" key."""
	if not set(WRITER_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only FoaMES Integration, FoaMES Engineer or System Manager may report topology"),
			frappe.PermissionError,
		)
	if report is None:
		fields.pop("cmd", None)
		report = fields
	if isinstance(report, str):
		report = json.loads(report)
	return apply_report(report, writable_tenants=_writable_tenants())


def _writable_tenants():
	"""None when the user may write any tenant, else the set they are restricted to."""
	from frappe.permissions import get_user_permissions

	allowed = get_user_permissions(frappe.session.user).get("Topology Tenant")
	if not allowed:
		return None
	return {p.get("doc") for p in allowed}


def apply_report(report, *, writable_tenants):
	try:
		named = _named_ids(report)
	except (AttributeError, TypeError):
		frappe.throw(_("The report must be an object with lists of assets, links and bindings"))
	try:
		clean = ingest_rules.normalize_report(
			report, store.existing_assets(named), writable_tenants=writable_tenants
		)
	except ingest_rules.ReportError as e:
		frappe.throw(_(str(e)))
	counts = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
	from foames.foames_topology.sync import _parents_first

	for values in _parents_first({a["asset_id"]: a for a in clean["assets"]}):
		counts[store.upsert_asset(values)] += 1
	for values in clean["links"]:
		counts[store.upsert_keyed("Topology Link", "link_key", values)] += 1
	for values in clean["bindings"]:
		counts[store.upsert_keyed("Signal Binding", "binding_key", values)] += 1
	if clean["retire_missing"]:
		counts["retired"] = store.retire_missing(
			clean["provider"],
			{a["asset_id"] for a in clean["assets"]},
			{x["link_key"] for x in clean["links"]},
			{x["binding_key"] for x in clean["bindings"]},
		)
	counts["rejected"] = clean["rejected"]
	return counts


def _named_ids(report):
	ids = set()
	for a in report.get("assets") or []:
		ids.update(x for x in (a.get("asset_id"), a.get("parent_asset")) if isinstance(x, str))
	for x in report.get("links") or []:
		ids.update(v for v in (x.get("from_asset"), x.get("to_asset")) if isinstance(v, str))
	for x in report.get("bindings") or []:
		ids.update(v for v in (x.get("signal"), x.get("physical_asset")) if isinstance(v, str))
	return ids


@frappe.whitelist(methods=["POST"])
def sync_now():
	frappe.only_for(("System Manager", "FoaMES Engineer"))
	from foames.foames_topology.sync import sync

	return sync()
