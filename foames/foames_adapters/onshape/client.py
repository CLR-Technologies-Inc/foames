# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A small read-only Onshape REST client.

Everything here imports nothing from Frappe. HTTP goes through an injected
`transport` callable — `(method, url, headers, body, timeout) -> (status,
response_headers, parsed_json_or_text)` — so tests run against `fake.py` and no
live credentials are ever needed. The client only issues GET requests: Onshape
writes are out of scope for this connector.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from foames.foames_adapters.onshape import auth, model

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)

# Onshape documents quota exhaustion and per-endpoint throttling.
STATUS_QUOTA_EXCEEDED = 402
STATUS_RATE_LIMITED = 429


class OnshapeError(Exception):
	"""Base class for connector failures; `retryable` marks transient ones."""

	retryable = False

	def __init__(self, message: str, *, status: int | None = None):
		super().__init__(message)
		self.status = status


class OnshapeAuthError(OnshapeError):
	"""401/403: bad, revoked or under-scoped credentials. Never retried."""


class OnshapeQuotaExceeded(OnshapeError):
	"""402: the account's annual API quota is exhausted. Not retried."""


class OnshapeRateLimited(OnshapeError):
	"""429: per-endpoint rate limit. Retried after the server's Retry-After."""

	retryable = True

	def __init__(self, message: str, *, status: int | None = None, retry_after: float | None = None):
		super().__init__(message, status=status)
		self.retry_after = retry_after


class OnshapeUnavailable(OnshapeError):
	"""5xx, timeouts and network failures. Retried with backoff."""

	retryable = True


@dataclass
class Connection:
	"""Where and how to reach Onshape. Secrets stay in Password fields upstream."""

	base_url: str = model.DEFAULT_BASE_URL
	access_key: str = ""
	secret_key: str = ""
	timeout: float = DEFAULT_TIMEOUT

	def __post_init__(self):
		self.base_url = (self.base_url or model.DEFAULT_BASE_URL).rstrip("/")


Transport = object  # callable; see module docstring


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
	"""The default transport: a real HTTPS request through urllib."""
	req = urllib.request.Request(url, data=body, headers=headers, method=method)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- operator-configured base URL
			raw = resp.read()
			return resp.status, dict(resp.headers), _parse_body(resp.headers.get("Content-Type", ""), raw)
	except urllib.error.HTTPError as e:
		raw = e.read() if e.fp else b""
		return e.code, dict(e.headers or {}), _parse_body(e.headers.get("Content-Type", "") if e.headers else "", raw)
	except (urllib.error.URLError, TimeoutError, OSError) as e:
		raise OnshapeUnavailable(str(e)) from e


def _parse_body(content_type: str, raw: bytes):
	if not raw:
		return None
	if "json" in content_type:
		try:
			return json.loads(raw.decode("utf-8"))
		except ValueError:
			return raw.decode("utf-8", errors="replace")
	return raw.decode("utf-8", errors="replace")


def error_from_response(status: int, payload, headers: dict | None = None) -> OnshapeError:
	"""Map an HTTP answer onto the connector's error classes.

	Classification follows the adapter rules: rejections (auth, quota) are
	permanent, rate limits and server errors are transient, anything unknown is
	treated as transient so the attempt cap is the backstop.
	"""
	headers = headers or {}
	message = _error_message(payload) or "HTTP {0}".format(status)
	if status in (401, 403):
		return OnshapeAuthError(message, status=status)
	if status == STATUS_QUOTA_EXCEEDED:
		return OnshapeQuotaExceeded(message, status=status)
	if status == STATUS_RATE_LIMITED:
		return OnshapeRateLimited(message, status=status, retry_after=_retry_after(headers))
	if status >= 500:
		return OnshapeUnavailable(message, status=status)
	return OnshapeError(message, status=status)


def _error_message(payload) -> str:
	if isinstance(payload, dict):
		for key in ("message", "error", "error_description", "detail"):
			if payload.get(key):
				return str(payload[key])
		if payload.get("errors"):
			return json.dumps(payload["errors"])[:500]
	return str(payload)[:500] if payload else ""


def _retry_after(headers: dict) -> float | None:
	for key, value in headers.items():
		if key.lower() == "retry-after":
			try:
				return max(0.0, float(value))
			except (TypeError, ValueError):
				return None
	return None


@dataclass
class OnshapeClient:
	"""Read-only client for the Onshape REST API v2 surface FoaMES uses."""

	connection: Connection
	transport: Transport = urllib_transport
	max_retries: int = MAX_RETRIES
	_sleep: object = time.sleep  # injectable for tests
	_now: object = time.time

	def request(self, method: str, path: str, params: dict | None = None) -> object:
		"""One signed GET. Only GET is supported; writes are out of scope by design."""
		if method != "GET":
			raise OnshapeError("The Onshape connector is read-only; only GET is allowed")
		url = self._url(path, params)
		attempt = 0
		while True:
			try:
				status, headers, payload = self.transport(
					method,
					url,
					auth.auth_headers(method, url, self.connection.access_key, self.connection.secret_key),
					None,
					self.connection.timeout,
				)
			except OnshapeUnavailable:
				raise
			except Exception as e:  # transport-level failure: transient
				raise OnshapeUnavailable(str(e)) from e
			if 200 <= status < 300:
				return payload
			error = error_from_response(status, payload, headers)
			if not error.retryable or attempt >= self.max_retries:
				raise error
			delay = error.retry_after if isinstance(error, OnshapeRateLimited) and error.retry_after is not None else RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
			self._sleep(delay)
			attempt += 1

	def _url(self, path: str, params: dict | None) -> str:
		query = urllib.parse.urlencode(params or {}, doseq=True)
		url = self.connection.base_url + path
		return url + ("?" + query if query else "")

	# -- Document reads -----------------------------------------------------

	def get_document(self, document_id: str) -> dict:
		"""GET /api/documents/{did}: name, default workspace, released version."""
		return self.request("GET", "/api/documents/{0}".format(document_id)) or {}

	def list_documents(self, owner_type: str = "company", owner_id: str = "", limit: int = 100) -> list:
		"""GET /api/documents: the documents the API key's owner can see."""
		params = {"ownerType": owner_type, "limit": limit}
		if owner_id:
			params["ownerId"] = owner_id
		payload = self.request("GET", "/api/documents", params)
		return payload if isinstance(payload, list) else (payload or {}).get("items", [])

	def get_elements(self, ref: model.CadReference) -> dict:
		"""GET the element list under the reference's document/wvm path."""
		return self.request("GET", ref.api_path() + "/elements") or {}

	def get_part_studio_elements(self, ref: model.CadReference) -> dict:
		return self.request("GET", ref.api_path() + "/partstudios") or {}

	def get_assembly_definition(self, ref: model.CadReference, assembly_id: str) -> dict:
		"""GET an assembly's structure where the account's plan exposes it."""
		return self.request("GET", ref.api_path() + "/assemblies/{0}".format(assembly_id)) or {}

	def get_user(self) -> dict:
		"""GET /api/users/me equivalent: proves the credentials work."""
		return self.request("GET", "/api/users/me") or {}

	def document_reference(self, document_id: str, base_url: str | None = None) -> model.CadReference:
		"""Fetch a document and return it as a pinned-or-workspace CadReference."""
		payload = self.get_document(document_id)
		return model.parse_document(payload, base_url or self.connection.base_url)
