# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Agent configurations and how one is run against a workspace.

An agent is a command line run in the workspace with the task prompt, so any coding agent with a
non-interactive mode fits: Claude Code, Codex CLI, Gemini CLI, OpenCode, Aider, or your own
script. Two built-in agents need nothing installed: `reference` applies the task's reference
solution (it validates the task and the grader) and `noop` changes nothing (the floor every
real agent must beat).
"""

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from foames_bench.paths import BENCH_ROOT

DEFAULT_CONFIG = BENCH_ROOT / "agents.json"


@dataclass
class Agent:
	name: str
	kind: str = "command"  # command, reference or noop
	command: list[str] = field(default_factory=list)
	stdin: bool = False
	model: str = ""
	tier: str = ""  # oss, baseline or frontier
	harness: str = ""
	usage_parser: str = "none"
	prices: dict | None = None
	env: dict = field(default_factory=dict)
	timeout_factor: float = 3.0
	# Local models: set 0.0 so runs count as costing nothing in tokens (electricity is not tracked).
	fixed_cost_usd: float | None = None
	notes: str = ""

	def available(self) -> tuple[bool, str]:
		if self.kind != "command":
			return True, "built in"
		exe = self.command[0] if self.command else ""
		if not exe:
			return False, "no command"
		return (True, shutil.which(exe)) if shutil.which(exe) else (False, f"{exe} not on PATH")


@dataclass
class RunResult:
	exit_code: int | None
	seconds: float
	timed_out: bool
	stdout: str
	stderr: str


def load(config: Path | None = None) -> dict[str, Agent]:
	data = json.loads(Path(config or DEFAULT_CONFIG).read_text(encoding="utf-8"))
	agents = {}
	for row in data["agents"]:
		row = {k: v for k, v in row.items() if not k.startswith("_")}
		agents[row["name"]] = Agent(**row)
	return agents


def _expand(arg: str, values: dict) -> str:
	for key, value in values.items():
		arg = arg.replace("{" + key + "}", value)
	return arg


def run(agent: Agent, task, workspace: Path, run_dir: Path) -> RunResult:
	"""Run the agent once in the workspace. Output goes to run_dir/agent.stdout and .stderr."""
	prompt = task.prompt
	prompt_file = run_dir / "prompt.md"
	prompt_file.write_text(prompt, encoding="utf-8")
	start = time.monotonic()
	if agent.kind == "noop":
		return RunResult(0, 0.0, False, "", "")
	if agent.kind == "reference":
		reference = task.module("reference")
		if reference is None:
			raise SystemExit(f"task {task.id} has no reference.py")
		reference.apply(workspace)
		return RunResult(0, time.monotonic() - start, False, "", "")

	values = {
		"prompt": prompt,
		"prompt_file": str(prompt_file),
		"workspace": str(workspace),
		"model": agent.model,
	}
	command = [_expand(a, values) for a in agent.command]
	env = {**os.environ, **{k: _expand(str(v), values) for k, v in agent.env.items()}}
	timeout = task.budget_seconds * agent.timeout_factor
	timed_out = False
	try:
		proc = subprocess.run(
			command,
			cwd=workspace,
			input=prompt if agent.stdin else None,
			stdin=None if agent.stdin else subprocess.DEVNULL,
			capture_output=True,
			text=True,
			env=env,
			timeout=timeout,
		)
		code, out, err = proc.returncode, proc.stdout, proc.stderr
	except subprocess.TimeoutExpired as e:
		timed_out, code = True, None
		out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
		err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
	except FileNotFoundError as e:
		code, out, err = 127, "", str(e)
	seconds = time.monotonic() - start
	(run_dir / "agent.stdout").write_text(out, encoding="utf-8")
	(run_dir / "agent.stderr").write_text(err, encoding="utf-8")
	return RunResult(code, seconds, timed_out, out, err)
