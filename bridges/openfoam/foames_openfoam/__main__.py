# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Command line for the OpenFOAM runner/provider.

	python -m foames_openfoam serve --config openfoam.json [--port 8765]
	python -m foames_openfoam run --config openfoam.json --case pitzdaily [--params '{"end_time": 300}']
	python -m foames_openfoam cases

`serve` starts the provider HTTP API. `run` executes one case synchronously in
the foreground (for smoke tests and the worker container's own checks).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from foames_openfoam.cases import BUILTIN_CASES
from foames_openfoam.manifest import ManifestError, validate_manifest
from foames_openfoam.runner import RunnerError, run_case
from foames_openfoam.service import Provider, serve

DEFAULT_TUTORIALS = os.environ.get("FOAM_TUTORIALS", "")


def _config(path: str) -> dict:
	if not path:
		return {}
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="python -m foames_openfoam", description=__doc__.splitlines()[0])
	sub = parser.add_subparsers(dest="command", required=True)
	for name in ("serve", "run", "cases"):
		p = sub.add_parser(name)
		p.add_argument("--config", default="", help="JSON configuration")
	serve_p = sub.choices["serve"]
	serve_p.add_argument("--host", default="127.0.0.1")
	serve_p.add_argument("--port", type=int, default=8765)
	run_p = sub.choices["run"]
	run_p.add_argument("--case", required=True)
	run_p.add_argument("--params", default="{}", help="JSON object of numeric params")
	return parser


def main(argv=None) -> int:
	args = build_parser().parse_args(argv)
	cfg = _config(args.config)
	work_root = cfg.get("work_root") or os.path.join(os.getcwd(), "openfoam-work")
	tutorials = cfg.get("tutorials_root") or DEFAULT_TUTORIALS
	if args.command == "cases":
		for spec in BUILTIN_CASES.values():
			print("{0}: {1} ({2}) params={3}".format(spec.name, spec.solver, spec.tutorial, ",".join(spec.params) or "-"))
		return 0
	if args.command == "serve":
		if not tutorials:
			print("tutorials_root (or FOAM_TUTORIALS) is required", file=sys.stderr)
			return 2
		provider = Provider(
			work_root, tutorials,
			token=os.environ.get(cfg.get("token_env") or "FOAMES_OPENFOAM_TOKEN", ""),
			command_timeout=float(cfg.get("command_timeout", 3600)),
			run_timeout=float(cfg.get("run_timeout", 14400)),
			solver_version=str(cfg.get("solver_version", "")),
		)
		serve(provider, host=args.host, port=args.port)
		return 0
	# run
	try:
		params = json.loads(args.params)
	except ValueError as e:
		print("--params is not valid JSON: {0}".format(e), file=sys.stderr)
		return 2
	try:
		manifest = validate_manifest({"case": args.case, "params": params}, known_cases=tuple(BUILTIN_CASES))
	except ManifestError as e:
		print(str(e), file=sys.stderr)
		return 2
	spec = BUILTIN_CASES[manifest["case"]]
	work_dir = os.path.join(work_root, "cli", manifest["case"])
	try:
		result = run_case(spec, manifest["params"], work_dir, tutorials_root=tutorials)
	except RunnerError as e:
		print("runner: {0}".format(e), file=sys.stderr)
		return 1
	print(json.dumps(result, indent=1, sort_keys=True))
	return 0 if result.get("status") == "succeeded" else 1


if __name__ == "__main__":
	sys.exit(main())
