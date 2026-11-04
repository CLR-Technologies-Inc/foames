# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Grade a finished run: hidden tests by group, the repository's own tests as regressions, the
tests the agent wrote, the scope of its change, purity of pure modules, and a written rubric for
tasks whose deliverable is a document."""

import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from foames_bench.paths import STUBS_DIR

RUNNER = Path(__file__).resolve().parent / "_unit_runner.py"
TEST_TIMEOUT = 300
ALWAYS_ALLOWED = ("BENCH_NOTES.md",)


def run_tests(files: list[Path], workspace: Path, timeout: int = TEST_TIMEOUT) -> list[dict]:
	"""Run unittest files against the workspace's code. Returns one row per test."""
	files = [str(f) for f in files if Path(f).exists()]
	if not files:
		return []
	with tempfile.TemporaryDirectory() as tmp:
		out = Path(tmp) / "results.json"
		env = {
			**os.environ,
			"PYTHONPATH": os.pathsep.join([str(workspace), str(STUBS_DIR)]),
			"PYTHONDONTWRITEBYTECODE": "1",
			"FOAMES_BENCH_WORKSPACE": str(workspace),
			"FOAMES_BENCH_STUBS": str(STUBS_DIR),
		}
		try:
			subprocess.run(
				[sys.executable, str(RUNNER), str(out), *files],
				cwd=tmp,
				env=env,
				capture_output=True,
				text=True,
				timeout=timeout,
			)
		except subprocess.TimeoutExpired:
			return [{"test": "timeout", "outcome": "error", "detail": f"tests ran over {timeout} s"}]
		if not out.exists():
			return [{"test": "runner", "outcome": "error", "detail": "the test runner wrote no result"}]
		return json.loads(out.read_text(encoding="utf-8"))


def pass_rate(rows: list[dict]) -> float | None:
	counted = [r for r in rows if r["outcome"] != "skip"]
	if not counted:
		return None
	return sum(r["outcome"] == "pass" for r in counted) / len(counted)


def _new_test_functions(patch: str) -> int:
	return len(re.findall(r"^\+\s*def test_\w+", patch, flags=re.MULTILINE))


def _in_scope(path: str, allowed: list[str]) -> bool:
	return path in ALWAYS_ALLOWED or any(fnmatch.fnmatch(path, pattern) for pattern in allowed)


def _imports_frappe(text: str) -> bool:
	return bool(re.search(r"^\s*(import frappe|from frappe\b)", text, flags=re.MULTILINE))


def purity_violations(workspace: Path, changed: list[dict], start_text) -> list[str]:
	"""Changed Python files that did not import Frappe at task start and do now (invariant 7)."""
	out = []
	for row in changed:
		path = row["path"]
		if not path.endswith(".py") or row["status"] == "D":
			continue
		before = start_text(path)
		if before is None or _imports_frappe(before):
			continue
		if _imports_frappe((workspace / path).read_text(encoding="utf-8", errors="replace")):
			out.append(path)
	return out


def rubric_score(workspace: Path, rubric: dict) -> dict:
	"""A deterministic floor for document deliverables: required sections, required concepts (each
	a list of regexes, any of which counts), and red flags that cost points. Use an LLM judge on
	top of it for a real assessment of the reasoning (docs/methodology.md)."""
	file = workspace / rubric["file"]
	if not file.exists():
		return {"score": 0.0, "missing_file": rubric["file"], "sections": {}, "concepts": {}, "red_flags": []}
	text = file.read_text(encoding="utf-8", errors="replace")
	headings = [h.strip().lower() for h in re.findall(r"^#{1,4}\s+(.+)$", text, flags=re.MULTILINE)]
	sections = {s: any(s.lower() in h for h in headings) for s in rubric.get("sections", [])}
	concepts = {}
	for concept in rubric.get("concepts", []):
		concepts[concept["id"]] = any(re.search(p, text, flags=re.IGNORECASE) for p in concept["any"])
	flags = [
		f["id"] for f in rubric.get("red_flags", []) if re.search(f["pattern"], text, flags=re.IGNORECASE)
	]
	weights = {c["id"]: c.get("weight", 1.0) for c in rubric.get("concepts", [])}
	section_part = sum(sections.values()) / len(sections) if sections else 1.0
	concept_total = sum(weights.values()) or 1.0
	concept_part = sum(weights[k] for k, hit in concepts.items() if hit) / concept_total
	penalty = rubric.get("red_flag_penalty", 0.15) * len(flags)
	score = max(0.0, 0.3 * section_part + 0.7 * concept_part - penalty)
	return {
		"score": round(score, 4),
		"sections": sections,
		"concepts": concepts,
		"red_flags": flags,
		"words": len(text.split()),
	}


def grade(task, workspace: Path, repo: Path, change: dict) -> dict:
	hidden = {
		group: run_tests([task.path / "hidden" / f for f in files], workspace)
		for group, files in task.hidden.items()
	}
	# The repository's own tests, taken from the pristine checkout so an agent cannot pass them by
	# editing them, run against the agent's code.
	regression = run_tests([repo / p for p in task.regression], workspace)

	changed = change["changed"]
	agent_test_files = [
		workspace / r["path"]
		for r in changed
		if r["status"] != "D" and re.search(r"(^|/)test_[^/]*\.py$", r["path"])
	]
	agent_tests = run_tests(agent_test_files, workspace)

	def start_text(path):
		result = subprocess.run(
			["git", "show", f"task-start:{path}"], cwd=workspace, capture_output=True, text=True
		)
		return result.stdout if result.returncode == 0 else None

	out_of_scope = [r["path"] for r in changed if not _in_scope(r["path"], task.allowed_paths)]
	deliverables = {d: (workspace / d).exists() for d in task.deliverables}
	notes = workspace / "BENCH_NOTES.md"
	rubric = None
	if task.rubric:
		rubric = rubric_score(workspace, json.loads((task.path / task.rubric).read_text(encoding="utf-8")))
	return {
		"hidden": {g: {"pass_rate": pass_rate(rows), "tests": rows} for g, rows in hidden.items()},
		"regression": {"pass_rate": pass_rate(regression), "tests": regression},
		"agent_tests": {
			"files": [str(p.relative_to(workspace)) for p in agent_test_files],
			"new_test_functions": _new_test_functions(change["patch"]),
			"pass_rate": pass_rate(agent_tests),
			"tests": agent_tests,
		},
		"changed_files": [r["path"] for r in changed],
		"out_of_scope": out_of_scope,
		"purity_violations": purity_violations(workspace, changed, start_text),
		"deliverables": deliverables,
		"notes_words": len(notes.read_text(encoding="utf-8", errors="replace").split())
		if notes.exists()
		else 0,
		"rubric": rubric,
	}
