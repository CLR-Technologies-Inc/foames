# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The provider service: a small HTTP API that accepts case manifests and runs them.

Endpoints (all JSON; mutating calls need `Authorization: Bearer <token>`):

    GET  /health                      liveness + solver version probe
    GET  /cases                       registered case names and descriptions
    POST /runs                        {"manifest": {...}, "requester": "..."} -> run record (202)
    GET  /runs/{id}                   run status, timestamps, result summary
    POST /runs/{id}/cancel            request cancellation at the next step boundary
    GET  /runs/{id}/artifacts         artifact names (logs)
    GET  /runs/{id}/artifacts/{name}  one artifact's content (confined to the run dir)

Runs execute on a worker thread; submission is idempotent via the manifest's
idempotency key. Standard library only.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from foames_openfoam.cases import BUILTIN_CASES, get_case
from foames_openfoam.lifecycle import Run, RunStore, idempotency_key, new_run_id
from foames_openfoam.manifest import ManifestError, config_hash, validate_manifest
from foames_openfoam.runner import Cancelled, RunnerError, request_cancel, run_case

API_VERSION = 1
MAX_BODY = 1024 * 1024


class Provider:
	"""Run registry + executor. One instance per service process."""

	def __init__(self, work_root: str, tutorials_root: str, *, token: str = "",
	             command_timeout: float = 3600.0, run_timeout: float = 14400.0,
	             solver_version: str = ""):
		self.store = RunStore(os.path.join(work_root, "runs"))
		self.work_root = work_root
		self.tutorials_root = tutorials_root
		self.token = token
		self.command_timeout = command_timeout
		self.run_timeout = run_timeout
		self.solver_version = solver_version
		self._threads = {}
		self._lock = threading.Lock()

	def submit(self, manifest: dict, requester: str = "") -> tuple:
		"""Validate + register a run; returns (run, created?). Idempotent."""
		clean = validate_manifest(manifest, known_cases=tuple(BUILTIN_CASES))
		key = idempotency_key(clean, requester)
		existing = self.store.find_by_key(key)
		if existing is not None:
			return existing, False
		spec = get_case(clean["case"])
		run = Run(
			run_id=new_run_id(),
			case=clean["case"],
			idempotency_key=key,
			status="queued",
			solver=spec.solver,
			solver_version=self.solver_version,
			config_hash=config_hash(clean, self.solver_version),
			requester=requester,
			work_dir=os.path.join(self.work_root, "work", new_run_id()),
		)
		# Stash the validated manifest on the run for the worker thread.
		run.result = {"manifest": clean}
		self.store.save(run)
		thread = threading.Thread(target=self._execute, args=(run.run_id,), daemon=True)
		with self._lock:
			self._threads[run.run_id] = thread
		thread.start()
		return run, True

	def _execute(self, run_id: str) -> None:
		run = self.store.load(run_id)
		if run is None:
			return
		manifest = (run.result or {}).get("manifest") or {}
		params = manifest.get("params") or {}
		spec = get_case(run.case)
		try:
			run.set_status("running")
			run.work_dir = os.path.join(self.work_root, "work", run.run_id)
			self.store.save(run)
			result = run_case(
				spec, params, run.work_dir,
				tutorials_root=self.tutorials_root,
				command_timeout=self.command_timeout,
				run_timeout=self.run_timeout,
			)
			status = result.pop("status")
			run.result = {**(run.result or {}), **result}
			run.set_status(status if status in ("succeeded", "failed", "timed_out") else "failed")
			if status == "timed_out":
				run.error = "run exceeded the time budget"
		except Cancelled:
			run.set_status("cancelled")
		except RunnerError as e:
			run.error = str(e)
			run.set_status("failed")
		except Exception as e:  # never leave a run stuck in running
			run.error = "{0}: {1}".format(type(e).__name__, e)
			run.set_status("failed")
		self.store.save(run)

	def cancel(self, run_id: str) -> Run | None:
		run = self.store.load(run_id)
		if run is None:
			return None
		if run.status == "queued":
			run.set_status("cancelled")
		elif run.status == "running":
			request_cancel(run.work_dir or os.path.join(self.work_root, "work", run.run_id))
		else:
			return run
		self.store.save(run)
		return run

	def artifact_names(self, run: Run) -> list:
		directory = run.work_dir or os.path.join(self.work_root, "work", run.run_id)
		return sorted(
			name for name in (run.result or {}).get("artifacts", [])
			if os.path.isfile(os.path.join(directory, name))
		)

	def artifact_path(self, run: Run, name: str) -> str | None:
		"""Confine artifact reads to the run's work directory."""
		if not name or "/" in name or "\\" in name or name.startswith("."):
			return None
		directory = os.path.abspath(run.work_dir or os.path.join(self.work_root, "work", run.run_id))
		path = os.path.abspath(os.path.join(directory, name))
		if os.path.commonpath([directory, path]) != directory or not os.path.isfile(path):
			return None
		return path


def make_handler(provider: Provider):
	class Handler(BaseHTTPRequestHandler):
		server_version = "FoaMESOpenFOAM/1"

		def _send(self, status: int, payload: dict):
			body = json.dumps(payload).encode("utf-8")
			self.send_response(status)
			self.send_header("Content-Type", "application/json")
			self.send_header("Content-Length", str(len(body)))
			self.end_headers()
			self.wfile.write(body)

		def _auth_ok(self) -> bool:
			if not provider.token:
				return True
			return self.headers.get("Authorization", "") == "Bearer " + provider.token

		def _read_json(self) -> dict:
			length = int(self.headers.get("Content-Length") or 0)
			if length <= 0 or length > MAX_BODY:
				return {}
			try:
				return json.loads(self.rfile.read(length).decode("utf-8"))
			except ValueError:
				return {}

		def do_GET(self):
			path = urlsplit(self.path).path
			if path == "/health":
				return self._send(200, {"ok": True, "api": API_VERSION, "cases": list(BUILTIN_CASES)})
			if not self._auth_ok():
				return self._send(401, {"ok": False, "error": "unauthorized"})
			if path == "/cases":
				return self._send(200, {"ok": True, "cases": [
					{"name": s.name, "solver": s.solver, "description": s.description, "params": list(s.params)}
					for s in BUILTIN_CASES.values()
				]})
			parts = [p for p in path.split("/") if p]
			if len(parts) == 2 and parts[0] == "runs":
				run = provider.store.load(unquote(parts[1]))
				return self._send(200, {"ok": True, "run": run.to_dict()}) if run else self._send(404, {"ok": False, "error": "not found"})
			if len(parts) == 4 and parts[0] == "runs" and parts[2] == "artifacts":
				run = provider.store.load(unquote(parts[1]))
				if run is None:
					return self._send(404, {"ok": False, "error": "not found"})
				name = unquote(parts[3])
				artifact = provider.artifact_path(run, name)
				if artifact is None:
					return self._send(404, {"ok": False, "error": "artifact not found"})
				with open(artifact, "rb") as f:
					body = f.read()
				self.send_response(200)
				self.send_header("Content-Type", "text/plain")
				self.send_header("Content-Length", str(len(body)))
				self.end_headers()
				self.wfile.write(body)
				return
			if len(parts) == 3 and parts[0] == "runs" and parts[2] == "artifacts":
				run = provider.store.load(unquote(parts[1]))
				if run is None:
					return self._send(404, {"ok": False, "error": "not found"})
				return self._send(200, {"ok": True, "artifacts": provider.artifact_names(run)})
			self._send(404, {"ok": False, "error": "not found"})

		def do_POST(self):
			path = urlsplit(self.path).path
			if not self._auth_ok():
				return self._send(401, {"ok": False, "error": "unauthorized"})
			if path == "/runs":
				data = self._read_json()
				try:
					run, created = provider.submit(data.get("manifest") or {}, requester=str(data.get("requester") or ""))
				except ManifestError as e:
					return self._send(400, {"ok": False, "error": str(e)})
				return self._send(202 if created else 200, {"ok": True, "run": run.to_dict(), "deduplicated": not created})
			parts = [p for p in path.split("/") if p]
			if len(parts) == 3 and parts[0] == "runs" and parts[2] == "cancel":
				run = provider.cancel(unquote(parts[1]))
				return self._send(200, {"ok": True, "run": run.to_dict()}) if run else self._send(404, {"ok": False, "error": "not found"})
			self._send(404, {"ok": False, "error": "not found"})

		def log_message(self, *args):
			pass

	return Handler


def serve(provider: Provider, host: str = "127.0.0.1", port: int = 8765) -> None:
	server = ThreadingHTTPServer((host, port), make_handler(provider))
	print("foames-openfoam provider on http://{0}:{1} (api v{2})".format(host, port, API_VERSION))
	server.serve_forever()
