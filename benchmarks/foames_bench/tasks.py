# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Task manifests. Each task is a folder under tasks/ with task.json, prompt.md, an optional
setup.py, hidden tests the agent never sees, and a reference solution used to validate the task.

A task may belong to a family (`"family": "sector-case-study"`): a folder `tasks/_<family>/` that
holds what its tasks share (setup.py, reference.py, a prompt.md appended to each task's own, a
rubric, and hidden tests). The task's own folder then needs only task.json, prompt.md and the
hidden data that makes it different; its files win where both folders have one."""

import importlib.util
import json
import shutil
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
	family: str | None = None

	@property
	def family_path(self) -> Path | None:
		return TASKS_DIR / f"_{self.family}" if self.family else None

	def _find(self, name: str) -> Path | None:
		"""A file from the task's folder, else from its family's folder."""
		for folder in (self.path, self.family_path):
			if folder is not None and (folder / name).exists():
				return folder / name
		return None

	@property
	def prompt(self) -> str:
		parts = [(self.path / "prompt.md").read_text(encoding="utf-8").rstrip()]
		if self.family_path and (self.family_path / "prompt.md").exists():
			parts.append((self.family_path / "prompt.md").read_text(encoding="utf-8").rstrip())
		parts.append((TASKS_DIR / "_common.md").read_text(encoding="utf-8"))
		return "\n\n".join(parts)

	@property
	def rubric_path(self) -> Path | None:
		return self._find(self.rubric) if self.rubric else None

	def module(self, name: str):
		"""Load setup.py or reference.py from the task folder (or its family's), or None when it has
		none. A family module finds its task's folder in the module attribute TASK_DIR."""
		file = self._find(f"{name}.py")
		if file is None:
			return None
		spec = importlib.util.spec_from_file_location(f"foames_bench_task_{self.id}_{name}", file)
		mod = importlib.util.module_from_spec(spec)
		mod.TASK_DIR = self.path
		spec.loader.exec_module(mod)
		return mod

	def hidden_dir(self, scratch: Path) -> Path:
		"""The folder the hidden tests run from. For a family task it is a copy, in `scratch`
		(outside the workspace), of the family's hidden folder with the task's own over it."""
		if not self.family_path:
			return self.path / "hidden"
		merged = scratch / "hidden"
		shared = self.family_path / "hidden"
		ignore = shutil.ignore_patterns("__pycache__")
		if shared.exists():
			shutil.copytree(shared, merged, ignore=ignore, dirs_exist_ok=True)
		if (self.path / "hidden").exists():
			shutil.copytree(self.path / "hidden", merged, ignore=ignore, dirs_exist_ok=True)
		return merged


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


def in_suite(task: Task, suite: str | None) -> bool:
	"""`core` is the tasks outside any family, a family's name is its tasks, `all` is every task."""
	if suite in (None, "all"):
		return True
	if suite == "core":
		return task.family is None
	return task.family == suite


def suites() -> list[str]:
	return ["core", *sorted({t.family for t in all_tasks() if t.family}), "all"]


def all_tasks(tier: str | None = None, suite: str | None = None) -> list[Task]:
	tasks = [load(p) for p in sorted(TASKS_DIR.iterdir()) if (p / "task.json").exists()]
	return [t for t in tasks if tier in (None, "all", t.tier) and in_suite(t, suite)]


def select(ids: list[str] | None, tier: str | None = None, suite: str | None = None) -> list[Task]:
	"""The named tasks, or with no names every task in the tier and suite."""
	tasks = all_tasks(tier, suite)
	if not ids:
		return tasks
	by_id = {t.id: t for t in all_tasks()}
	missing = [i for i in ids if i not in by_id]
	if missing:
		raise SystemExit(f"unknown task(s): {', '.join(missing)}; see `foames-bench list`")
	return [by_id[i] for i in ids]
