# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Tailnet hosts from `tailscale status --json`.

Every node (this machine and its peers) becomes a Host asset, Part Of the site given on the
command line if any, and joined to one Network Device asset for the tailnet by a Network link.
A peer that is online is OK with last_seen now; one that is offline is Down with Tailscale's own
LastSeen time. Nothing is changed on the tailnet: the collector only reads the status.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone


def slug(text: str) -> str:
	return re.sub(r"[^a-z0-9.-]+", "-", (text or "").lower()).strip("-") or "unnamed"


def host_id(name: str) -> str:
	return f"host:{slug(name)}"


def _time(value, fallback):
	if not value or str(value).startswith("0001-"):
		return fallback
	text = str(value).rstrip("Z").split(".")[0]
	try:
		return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
	except ValueError:
		return fallback


def read_status(path: str | None = None) -> dict:
	"""The status JSON, from a file (for tests and air-gapped runs) or the tailscale CLI."""
	if path:
		with open(path, encoding="utf-8") as f:
			return json.load(f)
	out = subprocess.run(["tailscale", "status", "--json"], check=True, capture_output=True, text=True)
	return json.loads(out.stdout)


def report_from_status(status: dict, *, provider: str, tenant: str | None = None, site: str | None = None, now: datetime | None = None) -> dict:
	now = now or datetime.now(timezone.utc).replace(tzinfo=None)
	stamp = now.strftime("%Y-%m-%d %H:%M:%S")
	tailnet = (status.get("CurrentTailnet") or {}).get("Name") or status.get("MagicDNSSuffix") or "tailnet"
	net_id = f"network:{slug(tailnet)}"
	assets = []
	if site:
		assets.append({"asset_id": f"site:{slug(site)}", "title": site, "kind": "Site", "status": "OK"})
	assets.append(
		{
			"asset_id": net_id,
			"title": tailnet,
			"kind": "Network Device",
			"status": "OK",
			"last_seen": stamp,
			"parent_asset": f"site:{slug(site)}" if site else None,
		}
	)
	links = []
	nodes = []
	if status.get("Self"):
		nodes.append((status["Self"], True))
	nodes += [(peer, False) for peer in (status.get("Peer") or {}).values()]
	seen = set()
	for node, is_self in nodes:
		name = node.get("HostName") or (node.get("DNSName") or "").split(".")[0]
		asset_id = host_id(name)
		if asset_id in seen:
			continue
		seen.add(asset_id)
		online = bool(node.get("Online")) or is_self
		assets.append(
			{
				"asset_id": asset_id,
				"title": name,
				"kind": "Host",
				"status": "OK" if online else "Down",
				"last_seen": stamp if online else _time(node.get("LastSeen"), None),
				"parent_asset": f"site:{slug(site)}" if site else None,
				"attributes": {
					"os": node.get("OS"),
					"dns_name": node.get("DNSName"),
					"addresses": node.get("TailscaleIPs") or [],
					"tags": node.get("Tags") or [],
				},
			}
		)
		links.append(
			{
				"from_asset": asset_id,
				"to_asset": net_id,
				"link_type": "Network",
				"status": "OK" if online else "Down",
				"last_seen": stamp if online else None,
			}
		)
	return {
		"provider": provider,
		"tenant": tenant,
		"assets": assets,
		"links": links,
		"bindings": [],
		"retire_missing": True,
	}
