# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI: python -m smells run manifest.json [--backend NAME] [--out DIR]"""

from __future__ import annotations

import argparse
import sys
import time

from .manifest import ManifestError, load
from .runner import run, write_result


def main(argv=None) -> int:
	t0 = time.perf_counter()
	parser = argparse.ArgumentParser(prog="smells", description="foaMES-smells benchmark harness")
	sub = parser.add_subparsers(dest="command", required=True)
	run_p = sub.add_parser("run", help="run one benchmark manifest")
	run_p.add_argument("manifest", help="path to manifest.json")
	run_p.add_argument("--backend", default="auto", help="python_ref | python_onnx | auto")
	run_p.add_argument("--out", default="results", help="output directory")
	args = parser.parse_args(argv)

	if args.command == "run":
		try:
			manifest = load(args.manifest)
			result = run(manifest, backend_name=args.backend, t0=t0)
		except (ManifestError, FileNotFoundError, ValueError) as e:
			print(f"smells: {e}", file=sys.stderr)
			return 2
		path = write_result(result, args.out)
		m = result["metrics"]
		lat = m["latency_ms"]
		print(
			f"{result['backend']['name']}: {m['inferences_per_s']:.1f} inf/s, "
			f"p95 {lat['p95']:.2f} ms, peak RSS {m['peak_rss_mb']:.1f} MB, "
			f"verdict {result['verdict']} -> {path}"
		)
		return 0 if result["verdict"] != "fail" else 1
	return 2


if __name__ == "__main__":
	sys.exit(main())
