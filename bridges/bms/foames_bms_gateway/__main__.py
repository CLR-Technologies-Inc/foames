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

"""Read building controllers and meters and post their points to FoaMES.

	python -m foames_bms_gateway check --config bms.json
	python -m foames_bms_gateway read  --config bms.json
	python -m foames_bms_gateway poll  --config bms.json --site https://foames.example.com --interval 60
	python -m foames_bms_gateway poll  --config bms.json --once --dry-run

The webhook secret is read from FOAMES_WEBHOOK_SECRET, so it appears in no file, shell history or
process list. The gateway only reads (BACnet ReadProperty, Modbus function codes 1 to 4); it never
writes a point, a setpoint or a command.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

from foames_bms_gateway import config
from foames_bms_gateway.poll import Readers, poll_once
from foames_bms_gateway.sender import SendError, WebhookSender


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="python -m foames_bms_gateway", description=__doc__.splitlines()[0])
	sub = parser.add_subparsers(dest="command", required=True)
	sub.add_parser("check", help="check the configuration and list the points it reads")
	sub.add_parser("read", help="read every point once and print the readings as JSON Lines")
	poll = sub.add_parser("poll", help="read the points and post them to FoaMES")
	poll.add_argument("--site", help="the FoaMES site URL (or the full webhook URL)")
	poll.add_argument("--interval", type=float, default=60, help="seconds between polls (default 60)")
	poll.add_argument("--once", action="store_true", help="poll once and exit")
	poll.add_argument("--dry-run", action="store_true", help="print what would be sent instead of sending it")
	for name in ("check", "read", "poll"):
		sub.choices[name].add_argument("--config", required=True, help="the gateway's JSON configuration")
	parser.add_argument("-v", "--verbose", action="store_true")
	return parser


def main(argv=None) -> int:
	args = build_parser().parse_args(argv)
	logging.basicConfig(
		level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
	)
	try:
		cfg = config.load(args.config)
	except config.ConfigError as e:
		print(f"configuration error: {e}", file=sys.stderr)
		return 2
	if args.command == "check":
		for point in cfg.points:
			device = cfg.devices[point.device]
			print(
				f"{point.point}: {device.protocol} {device.host}:{device.port} {json.dumps(point.spec, default=str)}"
			)
		return 0
	readers = Readers(cfg)
	try:
		if args.command == "read":
			readings, errors = poll_once(readers)
			for row in readings + errors:
				print(json.dumps(row))
			return 1 if errors and not readings else 0
		sender = None
		if not args.dry_run:
			if not args.site:
				print("--site is required unless --dry-run is given", file=sys.stderr)
				return 2
			sender = WebhookSender(args.site, os.environ.get("FOAMES_WEBHOOK_SECRET", ""))
		while True:
			readings, _errors = poll_once(readers)
			if sender is None:
				for row in readings:
					print(json.dumps(row))
			elif readings:
				try:
					answer = sender.send(readings)
					logging.info("sent %d, accepted %d", len(readings), len(answer.get("accepted") or []))
					for rejected in answer.get("rejected") or []:
						logging.warning("rejected %s", rejected)
				except SendError as e:
					logging.error("%s", e)
			if args.once:
				return 0
			time.sleep(max(args.interval, 1))
	except SendError as e:
		print(str(e), file=sys.stderr)
		return 1
	finally:
		readers.close()


if __name__ == "__main__":
	sys.exit(main())
