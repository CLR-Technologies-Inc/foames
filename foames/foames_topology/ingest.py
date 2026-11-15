# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Check a collector's report before it is written. No Frappe needed.

A collector (a plugin, an adapter, the network or agent-event collector in bridges/topology, or
any other app) reports what it sees as

	{
		"provider": "network-collector",
		"tenant": "Plant A",            # optional; the default for items that do not name one
		"assets":   [{"asset_id", "title", "layer", "kind", "parent_asset", "status", "last_seen",
		              "tenant", "attributes"}, ...],
		"links":    [{"from_asset", "to_asset", "link_type", "status", "last_seen", "tenant"}, ...],
		"bindings": [{"signal", "physical_asset", "direction", "unit", "tag", "last_value",
		              "last_value_at", "stale_after_seconds", "tenant"}, ...],
		"retire_missing": false        # true: the provider's assets not in this report are retired
	}

The rules that keep providers and tenants apart are applied here:

* every item is stamped with the reporting provider; whatever provider an item names is ignored;
* a provider may only change assets it provides. An asset another provider owns, an asset a
  person created by hand, and the built-in sync's assets are refused, item by item;
* the reserved sync provider names cannot be reported as;
* an item's tenant must be one the caller may write, and an existing asset never changes tenant;
* a link or binding may only join assets of the same tenant (or a shared, tenant-less one).

normalize_report() returns what to write and what was refused, with a reason for each refusal,
so a collector can log it. It never raises on a bad item, only on a bad report.
"""

from __future__ import annotations

from foames.foames_topology import model

MAX_ITEMS = 5000
ASSET_FIELDS = (
	"asset_id",
	"title",
	"layer",
	"kind",
	"parent_asset",
	"status",
	"last_seen",
	"tenant",
	"attributes",
)


class ReportError(ValueError):
	pass


def _clean_id(value, field):
	value = (value or "").strip() if isinstance(value, str) else value
	if not value or not isinstance(value, str):
		raise ValueError(f"{field} is required")
	if len(value) > 140:
		raise ValueError(f"{field} is longer than 140 characters")
	return value


def normalize_report(report: dict, existing: dict, *, writable_tenants=None) -> dict:
	"""existing: asset_id -> {"provider", "tenant", "managed"} for every asset the report names
	(as assets, parents, link ends or binding ends) that is already in the register.
	writable_tenants: the tenants the caller may write, or None for no restriction.

	Returns {"provider", "assets", "links", "bindings", "rejected", "retire_missing"}."""
	if not isinstance(report, dict):
		raise ReportError("the report must be an object")
	provider = (report.get("provider") or "").strip()
	if not provider:
		raise ReportError("provider is required")
	if provider in model.SYNC_PROVIDERS:
		raise ReportError(f"{provider} is reserved for FoaMES's own sync")
	if len(provider) > 140:
		raise ReportError("provider is longer than 140 characters")
	default_tenant = report.get("tenant") or None
	assets_in = report.get("assets") or []
	links_in = report.get("links") or []
	bindings_in = report.get("bindings") or []
	if sum(len(x) for x in (assets_in, links_in, bindings_in)) > MAX_ITEMS:
		raise ReportError(f"a report may hold at most {MAX_ITEMS} items; send it in parts")

	rejected = []
	assets = {}
	tenant_of = {k: v.get("tenant") for k, v in existing.items()}

	def tenant_ok(tenant):
		return writable_tenants is None or tenant is None or tenant in writable_tenants

	for item in assets_in:
		try:
			asset_id = _clean_id(item.get("asset_id"), "asset_id")
			kind = item.get("kind") or "Other"
			if kind not in model.KINDS:
				kind = "Other"
			layer = item.get("layer") or model.kind_layer(kind)
			if layer not in model.LAYERS:
				raise ValueError(f"layer must be one of {', '.join(model.LAYERS)}")
			status = item.get("status") or "Unknown"
			if status not in model.STATUSES:
				raise ValueError(f"status {status} is not one of {', '.join(model.STATUSES)}")
			tenant = item.get("tenant") or default_tenant
			current = existing.get(asset_id)
			if current is not None:
				if not current.get("managed"):
					raise ValueError("was created by hand; a collector cannot change it")
				if current.get("provider") != provider:
					raise ValueError(f"is provided by {current.get('provider')}")
				if (current.get("tenant") or None) != tenant:
					raise ValueError(f"belongs to tenant {current.get('tenant') or '(shared)'}")
			if not tenant_ok(tenant):
				raise ValueError(f"tenant {tenant} is not one you may write")
			clean = {k: item.get(k) for k in ASSET_FIELDS if item.get(k) not in (None, "")}
			clean.update(
				asset_id=asset_id, kind=kind, layer=layer, status=status, tenant=tenant, provider=provider
			)
			assets[asset_id] = clean
			tenant_of[asset_id] = tenant
		except ValueError as e:
			rejected.append({"type": "asset", "id": item.get("asset_id"), "reason": str(e)})

	known = set(existing) | set(assets)

	def check_pair(a, b):
		for end in (a, b):
			if end not in known:
				raise ValueError(f"{end} is not in the register or the report")
		ta, tb = tenant_of.get(a), tenant_of.get(b)
		if ta and tb and ta != tb:
			raise ValueError(f"joins tenant {ta} to tenant {tb}")
		return ta or tb or default_tenant

	for asset_id, item in list(assets.items()):
		parent = item.get("parent_asset")
		if parent:
			try:
				check_pair(parent, asset_id)
			except ValueError as e:
				rejected.append({"type": "asset", "id": asset_id, "reason": f"parent {parent}: {e}"})
				del assets[asset_id]

	links = []
	for item in links_in:
		try:
			a = _clean_id(item.get("from_asset"), "from_asset")
			b = _clean_id(item.get("to_asset"), "to_asset")
			link_type = item.get("link_type") or "Data Flow"
			if link_type not in model.LINK_TYPES:
				raise ValueError(f"link_type must be one of {', '.join(model.LINK_TYPES)}")
			if link_type == "Contains":
				raise ValueError("containment is set with parent_asset on the asset")
			tenant = check_pair(a, b)
			if not tenant_ok(tenant):
				raise ValueError(f"tenant {tenant} is not one you may write")
			links.append(
				{
					"link_key": f"{a}|{link_type}|{b}",
					"from_asset": a,
					"to_asset": b,
					"link_type": link_type,
					"status": item.get("status") or None,
					"last_seen": item.get("last_seen") or None,
					"tenant": tenant,
					"provider": provider,
				}
			)
		except ValueError as e:
			rejected.append(
				{"type": "link", "id": f"{item.get('from_asset')}→{item.get('to_asset')}", "reason": str(e)}
			)

	bindings = []
	layer_of = {k: v.get("layer") for k, v in existing.items()}
	layer_of.update({k: v["layer"] for k, v in assets.items()})
	for item in bindings_in:
		try:
			signal = _clean_id(item.get("signal"), "signal")
			physical = _clean_id(item.get("physical_asset"), "physical_asset")
			direction = item.get("direction") or "Read"
			if direction not in model.DIRECTIONS:
				raise ValueError("direction must be Read or Write")
			tenant = check_pair(signal, physical)
			problem = binding_problem(layer_of.get(signal), layer_of.get(physical))
			if problem:
				raise ValueError(problem)
			if not tenant_ok(tenant):
				raise ValueError(f"tenant {tenant} is not one you may write")
			bindings.append(
				{
					"binding_key": f"{signal}|{direction}|{physical}",
					"signal": signal,
					"physical_asset": physical,
					"direction": direction,
					"unit": item.get("unit") or None,
					"tag": item.get("tag") or None,
					"last_value": item.get("last_value"),
					"last_value_at": item.get("last_value_at") or None,
					"stale_after_seconds": item.get("stale_after_seconds") or None,
					"tenant": tenant,
					"provider": provider,
				}
			)
		except ValueError as e:
			rejected.append(
				{
					"type": "binding",
					"id": f"{item.get('signal')}→{item.get('physical_asset')}",
					"reason": str(e),
				}
			)

	return {
		"provider": provider,
		"assets": list(assets.values()),
		"links": links,
		"bindings": bindings,
		"rejected": rejected,
		"retire_missing": bool(report.get("retire_missing")),
	}


def binding_problem(signal_layer, physical_layer) -> str | None:
	"""Why a binding between nodes of these layers is wrong, or None. Used by the DocType too."""
	if signal_layer and signal_layer != model.DATA:
		return "the signal end of a binding must be a Data layer asset"
	if physical_layer and physical_layer != model.PHYSICAL:
		return "the physical end of a binding must be a Physical layer asset"
	return None
