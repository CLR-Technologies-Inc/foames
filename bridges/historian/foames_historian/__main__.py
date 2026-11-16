# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read process-historian tags and post them to FoaMES.

	python -m foames_historian check --config historian.json
	python -m foames_historian read  --config historian.json --tag "[default]L1/P1/Temp" --start now-1h
	python -m foames_historian read  --config historian.json --tag ... --interval 1m --aggregate mean
	python -m foames_historian sync  --config historian.json --checkpoint state.json --dry-run
	python -m foames_historian sync  --config historian.json --checkpoint state.json --site https://foames.example.com --follow 60
	python -m foames_historian sync  --config historian.json --start 2026-11-01T00:00Z --end 2026-11-02T00:00Z --site ...

The webhook secret is read from FOAMES_WEBHOOK_SECRET and the historian's password or token from
FOAMES_HISTORIAN_PASSWORD / FOAMES_HISTORIAN_TOKEN, so none appears in a file, the shell history
or the process list. The bridge only reads from the historian; it never writes a tag.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

from foames_historian import config
from foames_historian.model import AGGREGATES, UTC, HistorianError, iso, parse_duration, parse_time
from foames_historian.sender import SendError, WebhookSender
from foames_historian.sync import Checkpoint, sync_once


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="python -m foames_historian", description=__doc__.splitlines()[0])
	sub = parser.add_subparsers(dest="command", required=True)

	check = sub.add_parser(
		"check", help="read the last window of every mapped tag and report what it would send"
	)
	check.add_argument("--window", default="1h", help="how far back to look (default 1h)")

	read = sub.add_parser("read", help="print one tag's samples as JSON Lines")
	read.add_argument("--tag", required=True)
	read.add_argument(
		"--start", default="now-1h", help="ISO 8601, Unix seconds, or now-<duration> (default now-1h)"
	)
	read.add_argument("--end", default="now")
	read.add_argument("--interval", help="bucket length for an aggregate, such as 1m or 1h")
	read.add_argument("--aggregate", choices=AGGREGATES, help="default mean when --interval is given")

	sync = sub.add_parser("sync", help="post the mapped tags to FoaMES, from the checkpoint onwards")
	sync.add_argument("--site", help="the FoaMES site URL (or the full webhook URL)")
	sync.add_argument("--checkpoint", help="JSON file that remembers how far each tag was posted")
	sync.add_argument("--start", help="replay a fixed window from here (the checkpoint is left alone)")
	sync.add_argument("--end", help="end of the replayed window (default now)")
	sync.add_argument("--lag", default="2m", help="stay this far behind now, for late values (default 2m)")
	sync.add_argument(
		"--initial", default="1h", help="how far back a tag with no checkpoint starts (default 1h)"
	)
	sync.add_argument("--max-window", default="1d", help="longest window read per tag per pass (default 1d)")
	sync.add_argument(
		"--follow", type=float, metavar="SECONDS", help="keep syncing, pausing this long between passes"
	)
	sync.add_argument("--dry-run", action="store_true", help="print the events as JSON and post nothing")

	for p in (check, read, sync):
		p.add_argument("--config", required=True, help="the JSON configuration (source and tag map)")
		p.add_argument("-v", "--verbose", action="store_true")
	return parser


def main(argv=None, *, env=None, opener=None, sender=None, out=None, sleep=time.sleep) -> int:
	args = build_parser().parse_args(argv)
	env = os.environ if env is None else env
	out = out or sys.stdout
	logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
	try:
		source, mappings = config.load(args.config, env=env, opener=opener)
	except (HistorianError, ValueError) as e:
		print(f"configuration: {e}", file=sys.stderr)
		return 2
	try:
		with source:
			if args.command == "read":
				return _read(args, source, out)
			if args.command == "check":
				return _check(args, source, mappings, out)
			return _sync(args, source, mappings, env, sender, out, sleep)
	except (HistorianError, ValueError) as e:
		print(f"error: {e}", file=sys.stderr)
		return 1


def _read(args, source, out) -> int:
	now = datetime.now(UTC)
	start, end = parse_time(args.start, now=now), parse_time(args.end, now=now)
	interval = parse_duration(args.interval) if args.interval else None
	samples = source.read(args.tag, start, end, interval=interval, aggregate=args.aggregate)
	for s in samples:
		row = {"tag": s.tag, "timestamp": iso(s.timestamp), "value": s.value, "quality": s.quality}
		if s.units:
			row["units"] = s.units
		if s.extra:
			row.update({k: v for k, v in s.extra.items() if k not in row})
		out.write(json.dumps(row, default=str) + "\n")
	print(f"{len(samples)} samples", file=sys.stderr)
	return 0


def _check(args, source, mappings, out) -> int:
	now = datetime.now(UTC)
	result, events = sync_once(
		source,
		mappings,
		None,
		Checkpoint(None),
		now=now,
		start=now - parse_duration(args.window),
		end=now,
		dry_run=True,
	)
	by_tag = {}
	for event in events:
		by_tag[event["provenance"]["tag"]] = by_tag.get(event["provenance"]["tag"], 0) + 1
	for m in mappings:
		out.write(f"{m.tag} -> {m.machine} {m.type}: {by_tag.get(m.tag, 0)} events\n")
	for reason in result.errors:
		print(f"error {reason}", file=sys.stderr)
	for reason in result.skipped[:20]:
		print(f"skipped {reason}", file=sys.stderr)
	return 1 if result.errors else 0


def _sync(args, source, mappings, env, sender, out, sleep) -> int:
	if not args.dry_run and not args.site and sender is None:
		print("--site is needed unless --dry-run is given", file=sys.stderr)
		return 2
	if args.dry_run:
		send = None
	else:
		sender = sender or WebhookSender(args.site, env.get("FOAMES_WEBHOOK_SECRET", ""))
		send = sender.send
	checkpoint = Checkpoint(None if args.dry_run else args.checkpoint)
	options = {
		"lag": parse_duration(args.lag),
		"initial": parse_duration(args.initial),
		"max_window": parse_duration(args.max_window),
		"dry_run": args.dry_run,
	}
	if args.start:
		now = datetime.now(UTC)
		options["start"] = parse_time(args.start, now=now)
		options["end"] = parse_time(args.end, now=now) if args.end else now
	if args.follow and (args.start or args.dry_run):
		print("--follow cannot be combined with --start or --dry-run", file=sys.stderr)
		return 2

	status = 0
	while True:
		try:
			result, events = sync_once(source, mappings, send, checkpoint, **options)
		except SendError as e:
			print(f"error: {e}", file=sys.stderr)
			if not args.follow:
				return 1
			sleep(args.follow)
			continue
		if args.dry_run:
			json.dump(events, out, indent=1, default=str)
			out.write("\n")
		_report(result)
		status = 0 if result.ok else 1
		if not args.follow:
			return status
		if result.caught_up:
			sleep(args.follow)


def _report(result):
	print(
		f"read {result.read} samples, {result.events} events: accepted {result.accepted}, "
		f"already stored {result.duplicates}, rejected {len(result.rejected)}, skipped {len(result.skipped)}",
		file=sys.stderr,
	)
	for reason in result.errors:
		print(f"  error {reason}", file=sys.stderr)
	for r in result.rejected[:20]:
		print(f"  rejected {r.get('reason')}: {(r.get('event') or {}).get('id')}", file=sys.stderr)
	for reason in result.skipped[:20]:
		print(f"  skipped {reason}", file=sys.stderr)


if __name__ == "__main__":
	sys.exit(main())
