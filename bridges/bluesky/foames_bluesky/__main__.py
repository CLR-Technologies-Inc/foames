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

"""Replay finished Bluesky runs into FoaMES.

	python -m foames_bluesky jsonl run.jsonl --machine xrd-1 --summary mean --site https://foames.example.com
	python -m foames_bluesky tiled --uri https://tiled.example.org/api --uid 3f1c... --site ...
	python -m foames_bluesky jsonl run.jsonl --machine xrd-1 --dry-run     # print the events only

The webhook secret is read from the FOAMES_WEBHOOK_SECRET environment variable and a Tiled API key
from TILED_API_KEY, so neither appears in the shell history or the process list.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from foames_bluesky.mapping import SUMMARIES, RunMapper, map_documents
from foames_bluesky.sender import WebhookSender
from foames_bluesky.sources import jsonl_documents, tiled_documents


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="python -m foames_bluesky", description=__doc__.splitlines()[0])
	sub = parser.add_subparsers(dest="source", required=True)
	jsonl = sub.add_parser("jsonl", help="read [name, document] lines written by suitcase-jsonl")
	jsonl.add_argument("paths", nargs="+")
	tiled = sub.add_parser("tiled", help="read runs from a Tiled catalog of Bluesky runs")
	tiled.add_argument("--uri", required=True, help="the Tiled catalog URI")
	tiled.add_argument("--uid", action="append", required=True, help="a run uid; repeat for several")
	for p in (jsonl, tiled):
		p.add_argument("--site", help="the FoaMES site URL (or the full webhook URL)")
		p.add_argument("--machine", help="the FoaMES Machine Source ID; default: from the start document")
		p.add_argument("--machine-key", action="append", help="start-document key holding the Source ID")
		p.add_argument(
			"--stream", action="append", help="stream to read (default primary); 'all' for every one"
		)
		p.add_argument("--field", action="append", help="data key to read (default every numeric scalar)")
		p.add_argument("--prefix", default="", help="prefix for measurement names, such as 'xrd.'")
		p.add_argument("--summary", action="append", choices=SUMMARIES, help="per-run summary to post")
		p.add_argument("--no-readings", action="store_true", help="post only the summaries and messages")
		p.add_argument("--no-messages", action="store_true", help="skip the run start and stop messages")
		p.add_argument("--start-key", action="append", help="start-document key to keep in the provenance")
		p.add_argument("--dry-run", action="store_true", help="print the events as JSON and post nothing")
	return parser


def main(argv=None) -> int:
	args = build_parser().parse_args(argv)
	options = {
		"streams": None if args.stream and "all" in args.stream else (args.stream or ("primary",)),
		"fields": args.field,
		"prefix": args.prefix,
		"readings": not args.no_readings,
		"summaries": args.summary or (),
		"messages": not args.no_messages,
	}
	if args.machine_key:
		options["machine_keys"] = args.machine_key
	if args.start_key:
		options["start_keys"] = args.start_key
	mapper = RunMapper(args.machine, **options)

	if args.source == "jsonl":
		documents = (pair for path in args.paths for pair in jsonl_documents(path))
	else:
		documents = tiled_documents(args.uri, args.uid, api_key=os.environ.get("TILED_API_KEY"))
	events = map_documents(documents, mapper)
	for reason in mapper.skipped:
		print(f"skipped {reason}", file=sys.stderr)

	if args.dry_run:
		json.dump(events, sys.stdout, indent=1, default=str)
		print()
		return 0
	if not args.site:
		print("--site is needed unless --dry-run is given", file=sys.stderr)
		return 2
	sender = WebhookSender(args.site, os.environ.get("FOAMES_WEBHOOK_SECRET", ""))
	result = sender.send(events)
	duplicates = sum(1 for r in result["rejected"] if r.get("reason") == "duplicate event id")
	other = [r for r in result["rejected"] if r.get("reason") != "duplicate event id"]
	print(f"accepted {len(result['accepted'])}, already stored {duplicates}, rejected {len(other)}")
	for r in other[:20]:
		print(f"  {r.get('reason')}: {(r.get('event') or {}).get('id')}", file=sys.stderr)
	return 1 if other else 0


if __name__ == "__main__":
	sys.exit(main())
