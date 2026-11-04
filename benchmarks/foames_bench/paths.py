# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Where the benchmark, its tasks and the FoaMES checkout under test live."""

import os
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = BENCH_ROOT / "tasks"
DATA_DIR = BENCH_ROOT / "data"
STUBS_DIR = Path(__file__).resolve().parent / "stubs"


def repo_root(override: str | None = None) -> Path:
	"""The FoaMES checkout whose code the tasks start from: --repo, $FOAMES_REPO, or the parent of
	benchmarks/ when the benchmark sits inside a FoaMES clone."""
	candidate = override or os.environ.get("FOAMES_REPO") or str(BENCH_ROOT.parent)
	root = Path(candidate).expanduser().resolve()
	if not (root / "foames" / "hooks.py").exists():
		raise SystemExit(f"{root} is not a FoaMES checkout (no foames/hooks.py); pass --repo")
	return root
