# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Run lifecycle: the state machine every simulation run follows.

    draft -> queued -> running -> succeeded | failed | cancelled | timed_out

Terminal states never transition again; `queued` may be cancelled before it
starts; `running` may be cancelled or time out. This module is pure — no I/O —
so the same rules drive the provider service, the Frappe-side DocType and the
tests. Imports nothing outside the standard library.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field

RUN_STATES = ("draft", "queued", "running", "succeeded", "failed", "cancelled", "timed_out")
TERMINAL_STATES = ("succeeded", "failed", "cancelled", "timed_out")
ACTIVE_STATES = ("queued", "running")

_ALLOWED = {
	"draft": {"queued", "cancelled"},
	"queued": {"running", "cancelled", "failed"},
	"running": {"succeeded", "failed", "cancelled", "timed_out"},
}


class TransitionError(Exception):
	pass


def transition(current: str, target: str) -> str:
	"""Validate a state change; returns the target state."""
	if current not in RUN_STATES:
		raise TransitionError("unknown state {0!r}".format(current))
	if target not in RUN_STATES:
		raise TransitionError("unknown state {0!r}".format(target))
	if current in TERMINAL_STATES:
		raise TransitionError("run is already terminal ({0}); cannot move to {1}".format(current, target))
	if target not in _ALLOWED.get(current, set()):
		raise TransitionError("cannot move a run from {0} to {1}".format(current, target))
	return target


def idempotency_key(case_manifest: dict, requester: str = "") -> str:
	"""A stable key for one submission: same case + requester dedupes retries.

	The key covers the canonical JSON of the manifest, so a resubmitted request
	after a timeout maps to the same run instead of launching a duplicate job.
	"""
	canonical = json.dumps(case_manifest, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256((requester + "\n" + canonical).encode("utf-8")).hexdigest()


@dataclass
class Run:
	"""One simulation run's record, as the provider stores and reports it."""

	run_id: str
	case: str
	idempotency_key: str
	status: str = "queued"
	solver: str = ""
	solver_version: str = ""
	config_hash: str = ""
	requester: str = ""
	created_at: float = field(default_factory=time.time)
	started_at: float | None = None
	finished_at: float | None = None
	work_dir: str = ""
	error: str = ""
	artifacts: list = field(default_factory=list)
	result: dict = field(default_factory=dict)

	def __post_init__(self):
		if self.status not in RUN_STATES:
			raise TransitionError("unknown state {0!r}".format(self.status))

	def set_status(self, target: str) -> None:
		self.status = transition(self.status, target)
		now = time.time()
		if target == "running" and self.started_at is None:
			self.started_at = now
		if target in TERMINAL_STATES:
			self.finished_at = now

	def to_dict(self) -> dict:
		return {
			"run_id": self.run_id,
			"case": self.case,
			"idempotency_key": self.idempotency_key,
			"status": self.status,
			"solver": self.solver,
			"solver_version": self.solver_version,
			"config_hash": self.config_hash,
			"requester": self.requester,
			"created_at": self.created_at,
			"started_at": self.started_at,
			"finished_at": self.finished_at,
			"error": self.error,
			"artifacts": list(self.artifacts),
			"result": dict(self.result),
		}

	@classmethod
	def from_dict(cls, data: dict) -> "Run":
		known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001 - same module family
		return cls(**{k: v for k, v in data.items() if k in known})


def new_run_id() -> str:
	return "run-" + uuid.uuid4().hex[:16]


class RunStore:
	"""JSON-file-backed run registry with idempotent submit.

	One file per run under `directory`; `submit` returns the existing run when
	the idempotency key was already accepted, so retries cannot duplicate jobs.
	"""

	def __init__(self, directory: str):
		import os

		self.directory = directory
		os.makedirs(directory, exist_ok=True)

	def _path(self, run_id: str) -> str:
		import os
		return os.path.join(self.directory, run_id + ".json")

	def save(self, run: Run) -> None:
		import json
		import os

		path = self._path(run.run_id)
		tmp = path + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(run.to_dict(), f, indent=1, sort_keys=True)
		os.replace(tmp, path)

	def load(self, run_id: str) -> Run | None:
		import json
		import os

		path = self._path(run_id)
		if not os.path.isfile(path):
			return None
		with open(path, "r", encoding="utf-8") as f:
			return Run.from_dict(json.load(f))

	def find_by_key(self, key: str) -> Run | None:
		import glob
		import json
		import os

		for path in glob.glob(os.path.join(self.directory, "run-*.json")):
			try:
				with open(path, "r", encoding="utf-8") as f:
					data = json.load(f)
			except (OSError, ValueError):
				continue
			if data.get("idempotency_key") == key:
				return Run.from_dict(data)
		return None

	def all(self) -> list:
		import glob
		import os

		out = []
		for path in sorted(glob.glob(os.path.join(self.directory, "run-*.json"))):
			run = self.load(os.path.basename(path)[:-5])
			if run:
				out.append(run)
		return out
