# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read native WireGuard observations without requesting private or preshared keys.

Only the field-specific, script-friendly `wg show` interface is used. A recent handshake
is evidence of peer activity, not application health. Quiet peers remain Unknown.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import subprocess
from datetime import datetime, timezone

FIELDS = ("endpoints", "allowed-ips", "latest-handshakes", "transfer", "persistent-keepalive")


class StatusError(ValueError):
	"""An incomplete or invalid observation must never retire topology assets."""


def _utc(value: datetime) -> datetime:
	return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
	return value.strftime("%Y-%m-%d %H:%M:%S")


def _name(value) -> str:
	if not isinstance(value, str) or not value.strip() or len(value) > 140:
		raise StatusError("WireGuard names must contain 1 to 140 characters")
	return value.strip()


def _number(value) -> int:
	if isinstance(value, bool) or not isinstance(value, (int, str)):
		raise StatusError("WireGuard counters and times must be nonnegative integers")
	try:
		number = int(value)
	except ValueError:
		raise StatusError("WireGuard counters and times must be nonnegative integers") from None
	if not 0 <= number <= 2**64 - 1:
		raise StatusError("WireGuard counter or time is out of range")
	return number


def clean_status(status: dict) -> dict:
	"""Validate a snapshot and copy only known, non-secret fields; never echo rejected input."""
	try:
		observed = datetime.fromisoformat(status["observed_at"].replace("Z", "+00:00"))
		if observed.tzinfo is None or not isinstance(status["interfaces"], list):
			raise ValueError
		interfaces, names = [], set()
		for interface in status["interfaces"]:
			name = _name(interface["name"])
			if name in names or not isinstance(interface["peers"], list):
				raise ValueError
			names.add(name)
			peers, keys = [], set()
			for peer in interface["peers"]:
				key = peer["public_key"]
				decoded = base64.b64decode(key, validate=True)
				if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != key or key in keys:
					raise ValueError
				keys.add(key)
				endpoint = peer["endpoint"]
				if endpoint is not None and (not isinstance(endpoint, str) or len(endpoint) > 512):
					raise ValueError
				if not isinstance(peer["allowed_ips"], list):
					raise ValueError
				allowed = [str(ipaddress.ip_network(value, strict=False)) for value in peer["allowed_ips"]]
				latest = _number(peer["latest_handshake"])
				# Bound to a representable UTC timestamp even on Windows.
				if latest > 253402300799:
					raise ValueError
				keepalive = _number(peer["persistent_keepalive"])
				if keepalive > 65535:
					raise ValueError
				peers.append(
					{
						"public_key": key,
						"endpoint": endpoint,
						"allowed_ips": allowed,
						"latest_handshake": latest,
						"transfer_rx": _number(peer["transfer_rx"]),
						"transfer_tx": _number(peer["transfer_tx"]),
						"persistent_keepalive": keepalive,
					}
				)
			interfaces.append({"name": name, "peers": peers})
	except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
		raise StatusError("Invalid WireGuard status snapshot; no report was sent") from None
	return {"observed_at": _utc(observed).isoformat(), "interfaces": interfaces}


def _show(*args: str) -> str:
	try:
		result = subprocess.run(["wg", "show", *args], check=True, capture_output=True, text=True, timeout=10)
	except (OSError, subprocess.SubprocessError):
		raise StatusError(
			"Cannot read WireGuard status; check wg installation and read permissions"
		) from None
	# Some versions can return success alongside an error reading an interface.
	if result.stderr.strip():
		raise StatusError("WireGuard reported an incomplete observation; no report was sent")
	return result.stdout


def read_status(path: str | None = None) -> dict:
	if path:
		try:
			# The operator names the snapshot file on the command line.
			with open(path, encoding="utf-8") as stream:  # nosemgrep
				return clean_status(json.load(stream))
		except (OSError, ValueError, UnicodeError):
			raise StatusError("Cannot read a valid WireGuard status snapshot; no report was sent") from None

	interfaces = _show("interfaces").split()
	if len(set(interfaces)) != len(interfaces) or any(
		name in ("all", "interfaces", "help") or name.startswith("-") for name in interfaces
	):
		raise StatusError("Unsupported WireGuard interface name; no report was sent")
	rows = []
	for name in interfaces:
		tables = {}
		for field in FIELDS:
			table = {}
			for line in _show(name, field).splitlines():
				parts = line.split("\t")
				if len(parts) != (3 if field == "transfer" else 2) or parts[0] in table:
					raise StatusError("Invalid WireGuard field output; no report was sent")
				table[parts[0]] = parts[1:]
			tables[field] = table
		keys = set(tables["endpoints"])
		if any(set(table) != keys for table in tables.values()):
			raise StatusError("WireGuard peers changed during collection; retry the observation")
		peers = []
		for key in sorted(keys):
			endpoint = tables["endpoints"][key][0]
			allowed = tables["allowed-ips"][key][0]
			keepalive = tables["persistent-keepalive"][key][0]
			peers.append(
				{
					"public_key": key,
					"endpoint": None if endpoint == "(none)" else endpoint,
					"allowed_ips": [] if allowed == "(none)" else allowed.split(),
					"latest_handshake": tables["latest-handshakes"][key][0],
					"transfer_rx": tables["transfer"][key][0],
					"transfer_tx": tables["transfer"][key][1],
					"persistent_keepalive": 0 if keepalive == "off" else keepalive,
				}
			)
		rows.append({"name": name, "peers": peers})
	if set(_show("interfaces").split()) != set(interfaces):
		raise StatusError("WireGuard interfaces changed during collection; retry the observation")
	return clean_status({"observed_at": datetime.now(timezone.utc).isoformat(), "interfaces": rows})


def _id(kind: str, *parts: str) -> str:
	identity = json.dumps(parts, ensure_ascii=True).encode("utf-8")
	return f"wireguard-{kind}:{hashlib.sha256(identity).hexdigest()[:32]}"


def report_from_status(
	status: dict,
	*,
	provider: str,
	host: str,
	tenant: str | None = None,
	site: str | None = None,
	handshake_max_age: int = 180,
	now: datetime | None = None,
) -> dict:
	status = clean_status(status)
	provider, host = _name(provider), _name(host)
	if (
		not isinstance(handshake_max_age, int)
		or isinstance(handshake_max_age, bool)
		or handshake_max_age <= 0
	):
		raise StatusError("handshake-max-age must be a positive integer")
	now = _utc(now or datetime.now(timezone.utc))
	observed = datetime.fromisoformat(status["observed_at"])
	fresh = 0 <= (now - observed).total_seconds() <= handshake_max_age
	assets, links = [], []
	site_id = _id("site", provider, _name(site)) if site else None
	if site:
		assets.append({"asset_id": site_id, "title": site, "kind": "Site", "status": "Unknown"})
	for interface in status["interfaces"]:
		name = interface["name"]
		net_id = _id("interface", provider, host, name)
		assets.append(
			{
				"asset_id": net_id,
				"title": f"{host} / {name}",
				"kind": "Network Device",
				"status": "Unknown",
				"last_seen": _stamp(observed) if observed <= now else None,
				"parent_asset": site_id,
				"attributes": {
					"backend": "wireguard",
					"host": host,
					"interface": name,
					"observed_at": status["observed_at"],
				},
			}
		)
		for peer in interface["peers"]:
			peer_id = _id("peer", provider, host, name, peer["public_key"])
			latest = peer["latest_handshake"]
			age = now.timestamp() - latest if latest else None
			if not latest:
				health = "never"
			elif latest > observed.timestamp() or age < 0:
				health = "clock-skew"
			elif not fresh:
				health = "stale-observation"
			elif age > handshake_max_age:
				health = "stale"
			else:
				health = "recent"
			peer_status = "OK" if health == "recent" else "Unknown"
			last_seen = _stamp(datetime.fromtimestamp(latest, timezone.utc)) if latest and age >= 0 else None
			assets.append(
				{
					"asset_id": peer_id,
					"title": f"{name} peer {peer_id[-12:]}",
					"kind": "Host",
					"status": peer_status,
					"last_seen": last_seen,
					"parent_asset": site_id,
					"attributes": {
						**peer,
						"backend": "wireguard",
						"host": host,
						"interface": name,
						"observed_at": status["observed_at"],
						"handshake_age_seconds": age,
						"handshake_health": health,
					},
				}
			)
			links.append(
				{
					"from_asset": peer_id,
					"to_asset": net_id,
					"link_type": "Network",
					"status": peer_status,
					"last_seen": last_seen,
				}
			)
	return {
		"provider": provider,
		"tenant": tenant,
		"assets": assets,
		"links": links,
		"bindings": [],
		"retire_missing": fresh,
	}
