# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Case execution: run an allowlisted OpenFOAM pipeline in a confined directory.

The runner copies the case's tutorial directory into a per-run work directory,
applies only the manifest's declared numeric params to `system/controlDict`,
then runs the fixed command pipeline (`blockMesh`, `checkMesh`, the case's
solver, its extra steps and `postProcess`) with per-command timeouts. There is
no shell, no caller-supplied command and no path outside the work directory.
OpenFOAM binaries are expected on the worker's PATH (container or host install);
this module imports nothing outside the standard library.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

from foames_openfoam.cases import CaseSpec

CONTROL_DICT = os.path.join("system", "controlDict")
_PARAM_FIELDS = {"end_time": "endTime", "write_interval": "writeInterval"}
_SOLVING = re.compile(r"Solving for (\w+)")
_FINAL_RESIDUAL = re.compile(r"Final residual =\s*([0-9.eE+-]+)")


class RunnerError(Exception):
	pass


class Cancelled(Exception):
	pass


def _cancel_flag(work_dir: str) -> str:
	return os.path.join(work_dir, "CANCEL")


def request_cancel(work_dir: str) -> None:
	"""Ask a running job to stop at the next command boundary."""
	os.makedirs(work_dir, exist_ok=True)
	with open(_cancel_flag(work_dir), "w") as f:
		f.write("cancel")


def _check_cancel(work_dir: str) -> None:
	if os.path.exists(_cancel_flag(work_dir)):
		raise Cancelled()


def _apply_params(case_dir: str, spec: CaseSpec, params: dict) -> list:
	"""Write declared numeric params into the copied controlDict; returns what changed."""
	applied = []
	control = os.path.join(case_dir, CONTROL_DICT)
	if not params or not os.path.isfile(control):
		return applied
	with open(control, "r", encoding="utf-8", errors="replace") as f:
		text = f.read()
	for key, value in params.items():
		field = _PARAM_FIELDS.get(key)
		if field is None or field not in spec.params:
			continue
		pattern = re.compile(r"(\b" + re.escape(field) + r"\s+)[0-9.eE+-]+")
		new_text, count = pattern.subn(r"\g<1>{0:g}".format(float(value)), text, count=1)
		if count:
			text = new_text
			applied.append("{0}={1:g}".format(field, float(value)))
	with open(control, "w", encoding="utf-8") as f:
		f.write(text)
	return applied


def _run_command(cmd: list, cwd: str, log_path: str, timeout: float, work_dir: str) -> tuple:
	"""One allowlisted command; logs to file; returns (returncode, seconds)."""
	_check_cancel(work_dir)
	start = time.monotonic()
	with open(log_path, "w", encoding="utf-8", errors="replace") as log:
		try:
			proc = subprocess.run(
				cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
				timeout=timeout, check=False,
			)
			except subprocess.TimeoutExpired:
			return "timeout", time.monotonic() - start
		except FileNotFoundError as e:
			raise RunnerError("solver command not found: {0}".format(cmd[0])) from e
	return proc.returncode, time.monotonic() - start


def residual_summary(log_text: str) -> dict:
	"""Last 'Final residual' per solved field, from a solver log. Pure.

	OpenFOAM prints `Solving for <field>, Initial residual = .., Final residual = ..`
	on one line; the last occurrence per field wins.
	"""
	out = {}
	for line in log_text.splitlines():
		solving = _SOLVING.search(line)
		residual = _FINAL_RESIDUAL.search(line)
		if not solving or not residual:
			continue
		try:
			out[solving.group(1)] = float(residual.group(1))
		except ValueError:
			continue
	if not out:
		# Fallback: report the last final residual seen, field unnamed.
		matches = _FINAL_RESIDUAL.findall(log_text)
		if matches:
			try:
				out["last"] = float(matches[-1])
			except ValueError:
				pass
	return out


def run_case(spec: CaseSpec, params: dict, work_dir: str, *, tutorials_root: str,
	             command_timeout: float = 3600.0, run_timeout: float = 14400.0,
	             cancel_check=None) -> dict:
	"""Execute the case pipeline; returns result metadata. Raises RunnerError/Cancelled.

	`work_dir` is created fresh per run; `tutorials_root` is where the case's
	`tutorial` path resolves (the worker's $FOAM_TUTORIALS or a cases directory).
	"""
	case_src = os.path.join(tutorials_root, spec.tutorial)
	if not os.path.isdir(case_src):
		raise RunnerError("case files not found: {0}".format(case_src))
	os.makedirs(work_dir, exist_ok=True)
	case_dir = os.path.join(work_dir, "case")
	if os.path.exists(case_dir):
		shutil.rmtree(case_dir)
	shutil.copytree(case_src, case_dir, symlinks=False)
	applied = _apply_params(case_dir, spec, params)

	steps = ["blockMesh", "checkMesh", spec.solver, *spec.pipeline]
	logs, artifacts = [], []
	deadline = time.monotonic() + run_timeout
	mesh_ok = None
	for index, step in enumerate(steps):
		_check_cancel(work_dir)
		remaining = deadline - time.monotonic()
		if remaining <= 0:
			return {"status": "timed_out", "step": step, "logs": logs, "artifacts": artifacts}
		log_name = "{0:02d}-{1}.log".format(index, step)
		log_path = os.path.join(work_dir, log_name)
		code, seconds = _run_command(
			[step], case_dir, log_path, min(command_timeout, remaining), work_dir
		)
		logs.append({"step": step, "returncode": code, "seconds": round(seconds, 3), "log": log_name})
		artifacts.append(log_name)
		if code == "timeout":
			return {"status": "timed_out", "step": step, "logs": logs, "artifacts": artifacts}
		if index == 1:  # checkMesh
			mesh_ok = code == 0
			if not mesh_ok:
				return {"status": "failed", "step": step, "reason": "checkMesh failed", "logs": logs, "artifacts": artifacts}
		if code != 0:
			return {"status": "failed", "step": step, "reason": "{0} exited {1}".format(step, code), "logs": logs, "artifacts": artifacts}

	# Collect result fields: residuals from the solver log and postProcess output listing.
	solver_log = os.path.join(work_dir, "{0:02d}-{1}.log".format(steps.index(spec.solver), spec.solver))
	residuals = {}
	try:
		with open(solver_log, "r", encoding="utf-8", errors="replace") as f:
			residuals = residual_summary(f.read())
	except OSError:
		pass
	fields = []
	latest = os.path.join(case_dir, "postProcessing")
	if os.path.isdir(latest):
		fields = sorted(os.listdir(latest))[:200]
	return {
		"status": "succeeded",
		"mesh_ok": bool(mesh_ok),
		"params_applied": applied,
		"residuals": residuals,
		"postprocessed": fields,
		"logs": logs,
		"artifacts": artifacts,
	}
