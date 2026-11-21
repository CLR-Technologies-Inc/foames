# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Command line: health, capabilities and inspect for the FreeCAD bridge.

	python -m foames_freecad health      --config freecad.json
	python -m foames_freecad capabilities --config freecad.json
	python -m foames_freecad inspect     --config freecad.json part.FCStd
	python -m foames_freecad request     --config freecad.json   # one JSON envelope on stdin

`request` is the transport FoaMES (or any caller) uses: a versioned JSON request
on stdin, a versioned JSON response on stdout, exit code 0 on success.
"""

from __future__ import annotations

import argparse
import json
import sys

from foames_freecad import inspect as inspect_mod
from foames_freecad.config import Config, ConfigError
from foames_freecad.protocol import ACTIONS, BridgeError, Response, decode_request, encode


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="python -m foames_freecad", description=__doc__.splitlines()[0])
	sub = parser.add_subparsers(dest="command", required=True)
	for name in ("health", "capabilities", "inspect", "request"):
		p = sub.add_parser(name)
		p.add_argument("--config", help="JSON configuration (allowed_roots, freecad_python, limits)")
		p.add_argument("path", nargs="?", help="the .FCStd document (inspect only)")
	return parser


def _load(args) -> Config:
	if args.config:
		return Config.load(args.config)
	return Config()


def _capabilities(config: Config) -> dict:
	return {
		"protocol_version": 1,
		"actions": list(ACTIONS),
		"manifest_version": 1,
		"read_only": True,
		"max_bytes": config.max_bytes,
		"timeout_seconds": config.timeout_seconds,
		"freecad_python": config.freecad_python or "freecadcmd",
		"allowed_roots": config.allowed_roots,
	}


def _dispatch(request, config: Config) -> Response:
	if request.action == "health":
		return Response.success({"health": inspect_mod.health(config)})
	if request.action == "capabilities":
		return Response.success(_capabilities(config))
	# inspect
	path = request.params.get("path")
	if not path:
		raise BridgeError("bad_request", "inspect needs params.path")
	manifest = inspect_mod.inspect_document(str(path), config)
	return Response.success(manifest.to_dict())


def main(argv=None) -> int:
	args = build_parser().parse_args(argv)
	try:
		config = _load(args)
	except ConfigError as e:
		print(json.dumps(Response.failure(BridgeError("bad_request", str(e))).to_dict()))
		return 2
	try:
		if args.command == "request":
			request = decode_request(sys.stdin.read())
			response = _dispatch(request, config)
			print(encode(response))
			return 0 if response.ok else 1
		if args.command == "health":
			result = inspect_mod.health(config)
			print(json.dumps(result, indent=1, sort_keys=True))
			return 0 if result.get("available") else 1
		if args.command == "capabilities":
			print(json.dumps(_capabilities(config), indent=1, sort_keys=True))
			return 0
		if not args.path:
			print("inspect needs a .FCStd path", file=sys.stderr)
			return 2
		manifest = inspect_mod.inspect_document(args.path, config)
		print(json.dumps(manifest.to_dict(), indent=1, sort_keys=True))
		return 0
	except BridgeError as e:
		print(json.dumps(Response.failure(e).to_dict()))
		return 1
	except Exception as e:  # never traceback across the bridge boundary
		print(json.dumps(Response.failure(BridgeError("internal", str(e)[:500])).to_dict()))
		return 1


if __name__ == "__main__":
	sys.exit(main())
