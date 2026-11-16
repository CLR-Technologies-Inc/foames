# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Write the sector's case file and Machine Event export into the workspace. TASK_DIR is set by
the harness to the task's own folder, which holds hidden/sector.json."""

import importlib.util
import sys
from pathlib import Path

HIDDEN = Path(__file__).resolve().parent / "hidden"


def _fixture():
	if str(HIDDEN) not in sys.path:
		sys.path.insert(0, str(HIDDEN))
	spec = importlib.util.spec_from_file_location("_fixture", HIDDEN / "_fixture.py")
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def setup(workspace: Path):
	fixture = _fixture()
	sector = fixture.load_sector(Path(TASK_DIR) / "hidden" / "sector.json")  # noqa: F821 - set by the harness
	fixture.write(sector, workspace / "data" / "case")
