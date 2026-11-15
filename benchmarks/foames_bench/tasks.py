# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Task manifests. Each task is a folder under tasks/ with task.json, prompt.md, an optional
setup.py, hidden tests the agent never sees, and a reference solution used to validate the task."""

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

from foames_bench.paths import TASKS_DIR

GROUPS = ("functional", "invariant")


@dataclass
class Task:
	id: str
	title: str
	tier: str  # "pure" runs anywhere with Python; "frappe" needs the dev bench
	complexity: str  # low, medium, high
	trl_bands: list[str]
	dimension: str
	path: Path
	hidden: dict[str, list[str]]
	regression: list[str] = field(default_factory=list)
	allowed_paths: list[str] = field(default_factory=list)
	deliverables: list[str] = field(default_factory=list)
	budget_usd: float = 1.0
	budget_seconds: float = 900.0
	correctness_gate: float = 0.8
	rubric: str | None = None

	@property
	def prompt(self) -> str:
		own = (self.path / "prompt.md").read_text(encoding="utf-8").rstrip()
		common = (TASKS_DIR / "_common.md").read_text(encoding="utf-8")
		return own + "\n\n" + common

	def module(self, name: str):
		"""Load setup.py or reference.py from the task folder, or None when it has none."""
		file = self.path / f"{name}.py"
		if not file.exists():
			return None
		spec = importlib.util.spec_from_file_location(f"foames_bench_task_{self.id}_{name}", file)
		mod = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(mod)
		return mod


def load(path: Path) -> Task:
	data = json.loads((path / "task.json").read_text(encoding="utf-8"))
	budget = data.pop("budget", {})
	hidden = data.pop("hidden")
	unknown = set(hidden) - set(GROUPS)
	if unknown:
		raise ValueError(f"{path.name}: unknown hidden test groups {sorted(unknown)}")
	return Task(
		path=path,
		hidden=hidden,
		budget_usd=budget.get("usd", 1.0),
		budget_seconds=budget.get("seconds", 900.0),
		**data,
	)


def all_tasks(tier: str | None = None) -> list[Task]:
	tasks = [load(p) for p in sorted(TASKS_DIR.iterdir()) if (p / "task.json").exists()]
	return [t for t in tasks if tier in (None, "all", t.tier)]


def select(ids: list[str] | None, tier: str | None = None) -> list[Task]:
	tasks = all_tasks(tier)
	if not ids:
		return tasks
	by_id = {t.id: t for t in all_tasks()}
	missing = [i for i in ids if i not in by_id]
	if missing:
		raise SystemExit(f"unknown task(s): {', '.join(missing)}; see `foames-bench list`")
	return [by_id[i] for i in ids]
