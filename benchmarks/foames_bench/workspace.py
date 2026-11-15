# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A clean copy of FoaMES for one run. The copy leaves out benchmarks/ (so the hidden tests and the
reference solutions stay out of the agent's reach) and the original git history (so the task's
setup cannot be read back from a diff). It gets a one-commit git repository of its own, so the
agent can use git and the grader can take the patch."""

import shutil
import subprocess
from pathlib import Path

from foames_bench.paths import STUBS_DIR

EXCLUDE = {".git", "benchmarks", "node_modules", "__pycache__", ".venv", "runs", ".pytest_cache"}
GIT = [
	"git",
	"-c",
	"user.name=foames-bench",
	"-c",
	"user.email=bench@localhost",
	"-c",
	"commit.gpgsign=false",
]


def _ignore(directory, names):
	return [n for n in names if n in EXCLUDE or n.endswith(".pyc")]


def _git(workspace: Path, *args: str, check: bool = True) -> str:
	result = subprocess.run([*GIT, *args], cwd=workspace, capture_output=True, text=True, check=check)
	return result.stdout


def create(repo: Path, workspace: Path, task) -> Path:
	"""Copy the repository, apply the task's setup, and commit the starting point."""
	repo, workspace = repo.resolve(), workspace.resolve()
	if workspace == repo or workspace.is_relative_to(repo):
		inside = workspace.relative_to(repo).parts
		if not inside or inside[0] not in EXCLUDE:
			raise SystemExit(
				f"{workspace} is inside the FoaMES checkout and would be copied into itself; "
				"put run directories outside it or under benchmarks/runs"
			)
	# Clear the directory rather than remove it, so a sandbox's working directory can be prepared
	# in place.
	workspace.mkdir(parents=True, exist_ok=True)
	for child in workspace.iterdir():
		shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
	shutil.copytree(repo, workspace, ignore=_ignore, dirs_exist_ok=True)
	# The Frappe stub lets the agent run pure tests the same way the grader does.
	shutil.copytree(STUBS_DIR, workspace / ".foames-bench" / "stubs", ignore=_ignore)
	setup = task.module("setup")
	if setup:
		setup.setup(workspace)
	_git(workspace, "init", "-q", "-b", "main")
	_git(workspace, "add", "-A")
	_git(workspace, "commit", "-q", "-m", "Task start")
	_git(workspace, "tag", "task-start")
	return workspace


def collect(workspace: Path) -> dict:
	"""What the agent changed since the task started: the patch and the touched paths. Agents that
	commit and agents that leave changes in the working tree are treated alike."""
	_git(workspace, "add", "-A")
	# .foames-bench holds the harness's own files (prompt, Frappe stub, grading staging).
	paths = ["--", ".", ":(exclude)*.pyc", ":(exclude).foames-bench"]
	patch = _git(workspace, "diff", "--cached", "task-start", *paths)
	names = _git(workspace, "diff", "--cached", "--name-status", "task-start", *paths).splitlines()
	changed = []
	for line in names:
		parts = line.split("\t")
		if len(parts) >= 2:
			changed.append({"status": parts[0][0], "path": parts[-1]})
	return {"patch": patch, "changed": changed}
