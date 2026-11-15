# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Read the graph's records from the site and write managed ones back.

Reads go through frappe.get_list, so a user restricted to some tenants (a User Permission on
Topology Tenant) only ever gets those tenants' assets, links and bindings, plus shared ones. Writes
are only done for managed records (the sync's and collectors'), never for records made by hand.
"""

import json

import frappe
from frappe.utils import now_datetime

from foames.foames_topology import graph as topo

ASSET_FIELDS = [
	"name",
	"asset_id",
	"title",
	"layer",
	"kind",
	"parent_asset",
	"status",
	"last_seen",
	"disabled",
	"tenant",
	"provider",
	"managed",
	"source_doctype",
	"source_name",
]
LINK_FIELDS = ["link_key", "from_asset", "to_asset", "link_type", "status", "last_seen", "disabled", "tenant", "provider"]
BINDING_FIELDS = [
	"binding_key",
	"signal",
	"physical_asset",
	"direction",
	"unit",
	"tag",
	"last_value",
	"last_value_at",
	"stale_after_seconds",
	"disabled",
	"tenant",
	"provider",
]


SETTING_DEFAULTS = {
	"sync_enabled": 1,
	"default_tenant": None,
	"stale_after_seconds": 900,
	"include_erp_records": 1,
	"include_kpis": 1,
}


def settings() -> dict:
	"""Topology Settings with defaults for fields never saved (a fresh site has no row for them)."""
	stored = frappe.db.get_singles_dict("Topology Settings")
	return {k: (stored.get(k) if stored.get(k) not in (None, "") else v) for k, v in SETTING_DEFAULTS.items()}


def stale_after_seconds() -> int:
	return int(settings()["stale_after_seconds"] or 900)


def load_graph(*, include_disabled=False, user_scoped=True):
	"""The whole graph the current user may read."""
	reader = frappe.get_list if user_scoped else frappe.get_all
	filters = {} if include_disabled else {"disabled": 0}
	assets = reader("Topology Asset", filters=filters, fields=ASSET_FIELDS, limit_page_length=0)
	links = reader("Topology Link", filters=filters, fields=LINK_FIELDS, limit_page_length=0)
	# A link or binding that is itself enabled but points at a retired asset is still read: the graph
	# keeps it as a dangling edge, which findings() reports as drift.
	bindings = reader("Signal Binding", filters=filters, fields=BINDING_FIELDS, limit_page_length=0)
	return topo.build_graph(
		assets,
		links,
		bindings,
		now=now_datetime(),
		stale_after_seconds=stale_after_seconds(),
		include_disabled=include_disabled,
	)


def existing_assets(asset_ids):
	"""asset_id -> {provider, tenant, managed, layer} for those already in the register."""
	if not asset_ids:
		return {}
	rows = frappe.get_all(
		"Topology Asset",
		{"name": ("in", list(asset_ids))},
		["name", "provider", "tenant", "managed", "layer"],
	)
	return {r.name: {"provider": r.provider, "tenant": r.tenant, "managed": r.managed, "layer": r.layer} for r in rows}


def _same(doc, values):
	for key, value in values.items():
		current = doc.get(key)
		if key == "attributes" and value is not None and not isinstance(value, str):
			value = json.dumps(value, sort_keys=True, default=str)
		if str(current if current is not None else "") != str(value if value is not None else ""):
			return False
	return True


def upsert_asset(values: dict) -> str:
	"""Insert or update one managed asset. Returns inserted, updated, unchanged or skipped (a
	record made by hand, or one another provider owns, with the same id)."""
	values = dict(values)
	if isinstance(values.get("attributes"), (dict, list)):
		values["attributes"] = json.dumps(values["attributes"], sort_keys=True, default=str)
	values.setdefault("disabled", 0)
	name = values["asset_id"]
	if frappe.db.exists("Topology Asset", name):
		doc = frappe.get_doc("Topology Asset", name)
		if not doc.managed or (doc.provider and doc.provider != values.get("provider")):
			return "skipped"
		values.pop("asset_id")
		if _same(doc, values):
			return "unchanged"
		doc.update(values)
		doc.save(ignore_permissions=True)
		return "updated"
	frappe.get_doc({"doctype": "Topology Asset", "managed": 1, **values}).insert(ignore_permissions=True)
	return "inserted"


def upsert_keyed(doctype: str, key_field: str, values: dict) -> str:
	"""Insert or update one managed Topology Link or Signal Binding by its key."""
	values = dict(values)
	values.setdefault("disabled", 0)
	name = frappe.db.get_value(doctype, {key_field: values[key_field]}, "name")
	if name:
		doc = frappe.get_doc(doctype, name)
		if not doc.managed or (doc.provider and doc.provider != values.get("provider")):
			return "skipped"
		values.pop(key_field)
		if _same(doc, values):
			return "unchanged"
		doc.update(values)
		doc.save(ignore_permissions=True)
		return "updated"
	frappe.get_doc({"doctype": doctype, "managed": 1, **values}).insert(ignore_permissions=True)
	return "inserted"


def retire_missing(provider: str, keep_assets: set, keep_links: set, keep_bindings: set) -> int:
	"""Disable a provider's managed records that its latest full report or sync did not include.

	Retired, not deleted: an asset that left the register keeps its history, and anything still
	pointing at it shows up as drift."""
	count = 0
	for name in frappe.get_all(
		"Topology Asset", {"provider": provider, "managed": 1, "disabled": 0}, pluck="name"
	):
		if name not in keep_assets:
			frappe.db.set_value("Topology Asset", name, {"disabled": 1, "status": "Retired"})
			count += 1
	for doctype, key_field, keep in (
		("Topology Link", "link_key", keep_links),
		("Signal Binding", "binding_key", keep_bindings),
	):
		for row in frappe.get_all(
			doctype, {"provider": provider, "managed": 1, "disabled": 0}, ["name", key_field]
		):
			if row[key_field] not in keep:
				frappe.db.set_value(doctype, row.name, "disabled", 1)
				count += 1
	return count
