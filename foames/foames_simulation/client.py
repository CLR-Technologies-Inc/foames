# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP client for the foames-openfoam provider. Pure: injectable transport, no Frappe.

The provider contract (bridges/openfoam):

    GET  /health
    GET  /cases
    POST /runs                     {"manifest": {...}, "requester": "..."}
    GET  /runs/{id}
    POST /runs/{id}/cancel
    GET  /runs/{id}/artifacts
    GET  /runs/{id}/artifacts/{name}

Bearer-token auth when a token is configured. Transport is
`(method, url, headers, body_bytes, timeout) -> (status, headers, parsed)`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

DEFAULT_TIMEOUT = 30


class ProviderError(Exception):
	"""Provider call failed; `status` is the HTTP status when there was one."""

	def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
		super().__init__(message)
		self.status = status
		self.retryable = retryable


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
	req = urllib.request.Request(url, data=body, headers=headers, method=method)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- operator-configured URL
			raw = resp.read()
			return resp.status, dict(resp.headers), _parse(resp.headers.get("Content-Type", ""), raw)
	except urllib.error.HTTPError as e:
		raw = e.read() if e.fp else b""
		return e.code, dict(e.headers or {}), _parse(e.headers.get("Content-Type", "") if e.headers else "", raw)
	except (urllib.error.URLError, TimeoutError, OSError) as e:
	raise ProviderError(str(e), retryable=True) from e


def _parse(content_type: str, raw: bytes):
	if not raw:
		return None
	if "json" in content_type:
		try:
			return json.loads(raw.decode("utf-8"))
		except ValueError:
			pass
	return raw


@dataclass
class ProviderClient:
	base_url: str
	token: str = ""
	timeout: float = DEFAULT_TIMEOUT
	transport: object = urllib_transport

	def __post_init__(self):
		self.base_url = (self.base_url or "").rstrip("/")

	def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
		url = self.base_url + path
		headers = {"Accept": "application/json"}
		if payload is not None:
			headers["Content-Type"] = "application/json"
		body = json.dumps(payload).encode("utf-8") if payload is not None else None
		if self.token:
			headers["Authorization"] = "Bearer " + self.token
		try:
			status, _, data = self.transport(method, url, headers, body, self.timeout)
		except ProviderError:
			raise
		except Exception as e:
			raise ProviderError(str(e), retryable=True) from e
		if status == 401 or status == 403:
			raise ProviderError("provider rejected the token", status=status)
		if status == 404:
			raise ProviderError("provider has no such resource", status=status)
		if status == 400:
			raise ProviderError(_message(data) or "provider rejected the request", status=status)
		if status >= 500:
			raise ProviderError("provider error HTTP {0}".format(status), status=status, retryable=True)
		if not 200 <= status < 300:
			raise ProviderError("provider error HTTP {0}".format(status), status=status)
		if isinstance(data, dict):
			return data
		try:
			return json.loads(data.decode("utf-8")) if isinstance(data, (bytes, bytearray)) else {}
		except (ValueError, AttributeError):
			return {}

	def health(self) -> dict:
		return self._call("GET", "/health")

	def cases(self) -> list:
		return self._call("GET", "/cases").get("cases", [])

	def submit(self, manifest: dict, requester: str = "") -> dict:
		"""Submit a case manifest; the provider dedupes on the idempotency key."""
		return self._call("POST", "/runs", {"manifest": manifest, "requester": requester})

	def get_run(self, run_id: str) -> dict:
		return self._call("GET", "/runs/" + urllib.parse.quote(run_id, safe=""))

	def cancel(self, run_id: str) -> dict:
		return self._call("POST", "/runs/" + urllib.parse.quote(run_id, safe="") + "/cancel")

	def artifacts(self, run_id: str) -> list:
		return self._call("GET", "/runs/" + urllib.parse.quote(run_id, safe="") + "/artifacts").get("artifacts", [])


def _message(data) -> str:
	if isinstance(data, dict):
		return str(data.get("error") or data.get("message") or "")
	return ""
