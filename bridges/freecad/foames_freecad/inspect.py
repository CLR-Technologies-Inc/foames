# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Document inspection orchestration, FreeCAD-free.

`inspect_document` enforces the guardrails (path allowlist, size cap, timeout,
no macro execution), runs the probe in the configured FreeCAD runtime through
an injectable runner, and returns a validated manifest. The default runner
spawns `freecad_probe.py` under FreeCAD's own Python; tests inject a fake.
"""

from __future__ import annotations

import json
import os
import subprocess

from foames_freecad import manifest as manifest_mod
from foames_freecad import protocol
from foames_freecad.config import Config
from foames_freecad.manifest import Manifest, ManifestError

DOCUMENT_SUFFIX = ".FCStd"


class InspectError(Exception):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code
		self.message = message


def check_path(path: str, config: Config) -> str:
	"""Resolve and confine `path`: .FCStd suffix, inside an allowed root, a real file."""
	candidate = os.path.abspath(os.path.expanduser(path))
	if not candidate.lower().endswith(DOCUMENT_SUFFIX):
		raise InspectError(protocol.ERR_PATH_REJECTED, "only .FCStd documents can be inspected")
	if config.allowed_roots:
		if not any(_within(candidate, root) for root in config.allowed_roots):
			raise InspectError(
				protocol.ERR_PATH_REJECTED,
				"{0} is outside the configured allowed_roots".format(candidate),
			)
	else:
		# No roots configured: only the current directory and below.
		if not _within(candidate, os.getcwd()):
			raise InspectError(protocol.ERR_PATH_REJECTED, "{0} is outside the working directory".format(candidate))
	if not os.path.isfile(candidate):
		raise InspectError(protocol.ERR_DOCUMENT_UNREADABLE, "{0} is not a readable file".format(candidate))
	return candidate


def _within(path: str, root: str) -> bool:
	root = os.path.abspath(root)
	return path == root or path.startswith(root + os.sep)


def check_size(path: str, config: Config) -> int:
	size = os.path.getsize(path)
	if size > config.max_bytes:
		raise InspectError(
			protocol.ERR_TOO_LARGE,
			"{0} is {1} bytes; the limit is {2}".format(path, size, config.max_bytes),
		)
	if size == 0:
		raise InspectError(protocol.ERR_DOCUMENT_UNREADABLE, "{0} is empty".format(path))
	return size


def subprocess_runner(config: Config):
	"""The real runner: `freecad_python freecad_probe.py <doc>` -> (stdout, stderr)."""
	python = config.freecad_python or "freecadcmd"

	def run(path: str, timeout: float):
		cmd = [python, config.probe(), path]
		try:
			proc = subprocess.run(
				cmd,
				capture_output=True,
				text=True,
				timeout=timeout,
				check=False,
			)
		except FileNotFoundError as e:
			raise InspectError(protocol.ERR_FREECAD_MISSING, "FreeCAD runtime not found: {0}".format(python)) from e
		except subprocess.TimeoutExpired as e:
			raise InspectError(protocol.ERR_TIMEOUT, "inspection exceeded {0}s".format(timeout)) from e
		return proc.stdout, proc.stderr, proc.returncode

	return run


def inspect_document(path: str, config: Config, runner=None) -> Manifest:
	"""Inspect one .FCStd and return its manifest. Read-only: the source is never modified."""
	resolved = check_path(path, config)
	size = check_size(resolved, config)
	runner = runner or subprocess_runner(config)
	try:
		stdout, stderr, code = runner(resolved, config.timeout_seconds)
	except InspectError:
		raise
	except Exception as e:
		raise InspectError(protocol.ERR_INTERNAL, "probe failed: {0}".format(e)) from e
	if code != 0:
		raise InspectError(protocol.ERR_DOCUMENT_UNREADABLE, _probe_error(stderr, stdout))
	try:
		payload = json.loads(stdout)
	except ValueError as e:
		raise InspectError(protocol.ERR_DOCUMENT_UNREADABLE, "probe did not return JSON: {0}".format(e)) from e
	try:
		return manifest_mod.build_manifest(resolved, payload, byte_size=size)
	except ManifestError as e:
		raise InspectError(protocol.ERR_INTERNAL, "bad manifest: {0}".format(e)) from e


def _probe_error(stderr: str, stdout: str) -> str:
	tail = (stderr or stdout or "").strip().splitlines()
	return tail[-1][:500] if tail else "the FreeCAD probe failed"


def document_digest(path: str) -> str:
	return manifest_mod.sha256_file(path)


def health(config: Config, runner=None) -> dict:
	"""Report whether a FreeCAD runtime answers, without touching any document."""
	if runner is not None:
		stdout, _, code = runner("", 15.0)
		if code != 0:
			return {"available": False, "detail": "probe exited nonzero"}
		try:
			payload = json.loads(stdout)
		except ValueError:
			return {"available": False, "detail": "probe did not return JSON"}
		return {"available": True, **{k: payload.get(k) for k in ("freecad_version", "python_version") if payload.get(k)}}
	python = config.freecad_python or "freecadcmd"
	try:
		proc = subprocess.run(
			[python, "--version"], capture_output=True, text=True, timeout=15, check=False
		)
	except FileNotFoundError:
		return {"available": False, "detail": "FreeCAD runtime not found: {0}".format(python)}
	except subprocess.TimeoutExpired:
		return {"available": False, "detail": "FreeCAD --version timed out"}
	text = (proc.stdout or proc.stderr or "").strip()
	return {"available": proc.returncode == 0, "detail": text[:300]}
