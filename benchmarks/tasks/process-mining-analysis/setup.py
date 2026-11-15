"""Write the synthetic event log into the workspace."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("pm_fixture", Path(__file__).with_name("fixture.py"))
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def setup(workspace: Path):
	target = workspace / "data" / "weld_cell_events.csv"
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(fixture.to_csv(fixture.rows()), encoding="utf-8")
