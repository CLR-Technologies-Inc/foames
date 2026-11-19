# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""foames-topology-collect network|wireguard|agents …

	foames-topology-collect network --provider network-collector --site-name "Plant A" \
		--url https://foames.example.com
	foames-topology-collect agents --provider agent-events --log agents.jsonl --url …

The API key and secret come from FOAMES_API_KEY and FOAMES_API_SECRET. With --dry-run the report
is printed instead of sent. Run it from cron or a systemd timer to keep the graph current."""

from __future__ import annotations

import argparse
import json
import os
import sys

from foames_topology_collectors import agents, network, sender, wireguard


def main(argv=None) -> int:
	parser = argparse.ArgumentParser(prog="foames-topology-collect")
	sub = parser.add_subparsers(dest="collector", required=True)
	for name in ("network", "wireguard", "agents"):
		p = sub.add_parser(name)
		p.add_argument("--provider", required=True, help="the provider name this collector reports as")
		p.add_argument("--tenant", help="the Topology Tenant the items belong to (empty: shared)")
		p.add_argument("--url", help="the FoaMES site URL")
		p.add_argument("--dry-run", action="store_true", help="print the report instead of sending it")
		if name == "network":
			p.add_argument("--status-file", help="read `tailscale status --json` output from this file")
			p.add_argument("--site-name", help="a Site asset the hosts are Part Of")
		elif name == "wireguard":
			p.add_argument("--host-name", required=True, help="stable name of the gateway being observed")
			p.add_argument("--site-name", help="a Site asset scoped to this WireGuard provider")
			p.add_argument("--status-file", help="read a sanitized WireGuard JSON snapshot instead of wg")
			p.add_argument(
				"--snapshot", action="store_true", help="print sanitized status JSON for later replay"
			)
			p.add_argument(
				"--handshake-max-age", type=int, default=180, help="recent handshake window in seconds"
			)
		else:
			p.add_argument("--log", required=True, help="the JSON Lines event log ('-' for stdin)")
			p.add_argument("--window-hours", type=float, default=24, help="only tasks seen in this window")
	args = parser.parse_args(argv)

	if args.collector == "network":
		report = network.report_from_status(
			network.read_status(args.status_file),
			provider=args.provider,
			tenant=args.tenant,
			site=args.site_name,
		)
	elif args.collector == "wireguard":
		if args.handshake_max_age <= 0:
			parser.error("--handshake-max-age must be positive")
		if args.snapshot and args.url:
			parser.error("--snapshot cannot be combined with --url")
		try:
			status = wireguard.read_status(args.status_file)
			report = wireguard.report_from_status(
				status,
				provider=args.provider,
				host=args.host_name,
				tenant=args.tenant,
				site=args.site_name,
				handshake_max_age=args.handshake_max_age,
			)
		except wireguard.StatusError as error:
			print(str(error), file=sys.stderr)
			return 2
		if args.snapshot:
			json.dump(status, sys.stdout, indent=1)
			print()
			return 0
	else:
		# The operator names the file on the command line.
		stream = sys.stdin if args.log == "-" else open(args.log, encoding="utf-8")  # nosemgrep
		with stream:
			events, skipped = agents.read_events(stream)
		if skipped:
			print(f"skipped {skipped} lines that are not agent events", file=sys.stderr)
		report = agents.report_from_events(
			events, provider=args.provider, tenant=args.tenant, window_hours=args.window_hours
		)

	if args.dry_run or not args.url:
		json.dump(report, sys.stdout, indent=1, default=str)
		print()
		return 0
	key, secret = os.environ.get("FOAMES_API_KEY"), os.environ.get("FOAMES_API_SECRET")
	if not key or not secret:
		print("set FOAMES_API_KEY and FOAMES_API_SECRET", file=sys.stderr)
		return 2
	result = sender.send(report, args.url, key, secret)
	json.dump(result, sys.stdout, indent=1, default=str)
	print()
	return 1 if result.get("rejected") else 0


if __name__ == "__main__":
	sys.exit(main())
