# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A small REST client for the Insights Hub platform APIs, using only the standard library.

Every Insights Hub API sits behind the region gateway as `https://gateway.<region>/api/<service>/
v<n>/<resource>`, answers JSON, and reports failures as `{"errors": [{"code", "message",
"logref"}]}`. Collections are paged with `page` and `size` and come back as `{"_embedded": {<name>:
[...]}, "page": {"number", "size", "totalElements", "totalPages"}}`. Two ways of getting a bearer
token are supported:

- **Technical Token Manager**: the way an application registered on the tenant gets a token. A POST
  to `technicaltokenmanager/v3/oauth/token` carries the app's client id and secret, base64-encoded,
  in the `X-SPACE-AUTH-KEY` header (`Basic <credentials>` as the platform SDKs send it; the scheme
  is configurable because documentation versions differ) and names the app and the host and user
  tenants in the body.
- **Service Credentials**: plain OAuth 2.0 client credentials against the tenant's identity provider
  (`https://<tenant>.piam.<region>/oauth/token`), with the client id and secret as Basic auth.

The HTTP call itself goes through a transport function, so tests can run without a tenant.
"""

from __future__ import annotations

import base64
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


@dataclass
class Response:
	status: int
	headers: dict
	body: bytes = b""

	def header(self, name: str) -> str | None:
		name = name.lower()
		for key, value in self.headers.items():
			if key.lower() == name:
				return value
		return None

	def json(self):
		return json.loads(self.body.decode("utf-8")) if self.body else None


class InsightsHubError(Exception):
	"""Insights Hub answered with an error, or could not be reached.

	`transient` is True when trying again later may succeed (server errors, throttling, timeouts,
	network failures, a rejected login). Validation errors (a bad payload, an asset that does not
	exist, a property the aspect does not have) are not transient: they need a person to fix the data.

	`maybe_applied` is True when a write may have reached Insights Hub before the failure, so a retry
	must first check whether it was applied.
	"""

	def __init__(self, message, status=None, code=None, details=None, transient=False, maybe_applied=False):
		super().__init__(message)
		self.status = status
		self.code = code
		self.details = details or []
		self.transient = transient
		self.maybe_applied = maybe_applied


TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
# A rejected login cannot have applied a write and clears up when the credentials are fixed, so the
# outbox retries it instead of failing the posting and holding its sequence group.
AUTH_STATUSES = {401, 403}

TOKEN_MANAGER = "Technical Token Manager"
SERVICE_CREDENTIALS = "Service Credentials"
TOKEN_MANAGER_PATH = "technicaltokenmanager/v3/oauth/token"


def urllib_transport(cafile: str | None = None):
	"""Default transport: urllib over TLS with the host's CA store, or a given CA file."""
	context = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
	opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

	def send(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> Response:
		request = urllib.request.Request(url, data=body, headers=headers, method=method)
		try:
			with opener.open(request, timeout=timeout) as response:
				return Response(response.status, dict(response.headers.items()), response.read())
		except urllib.error.HTTPError as e:
			return Response(e.code, dict(e.headers.items()) if e.headers else {}, e.read() or b"")

	return send


@dataclass
class Connection:
	"""Where and how to reach one Insights Hub tenant."""

	gateway_url: str  # https://gateway.eu1.mindsphere.io
	tenant: str = ""
	auth: str = TOKEN_MANAGER
	client_id: str = ""
	client_secret: str = ""
	# Technical Token Manager: the registered application and the tenants it runs for.
	app_name: str = ""
	app_version: str = ""
	host_tenant: str = ""
	user_tenant: str = ""
	token_manager_scheme: str = "Basic"  # the scheme word in X-SPACE-AUTH-KEY
	# Service Credentials: the tenant's token endpoint.
	token_url: str = ""
	timeout: float = 30.0
	cafile: str | None = None
	extra: dict = field(default_factory=dict)


class RestClient:
	def __init__(self, connection: Connection, transport=None):
		self.connection = connection
		self.transport = transport or urllib_transport(connection.cafile)
		self._token: tuple[str, float] | None = None

	# URLs

	def url(self, path: str, query: dict | None = None) -> str:
		"""`<gateway>/api/<path>`, with the query values URL-encoded (JSON filters included)."""
		url = self.connection.gateway_url.rstrip("/") + "/api/" + path.lstrip("/")
		if query:
			url += "?" + urllib.parse.urlencode(
				{k: v for k, v in query.items() if v is not None}, quote_via=urllib.parse.quote
			)
		return url

	# Authentication

	def access_token(self) -> str:
		if self._token and self._token[1] > time.time() + 30:
			return self._token[0]
		c = self.connection
		basic = base64.b64encode(f"{c.client_id}:{c.client_secret}".encode()).decode("ascii")
		if c.auth == SERVICE_CREDENTIALS:
			if not c.token_url:
				raise InsightsHubError("Service Credentials need a token URL")
			response = self.send(
				"POST",
				c.token_url,
				{
					"Authorization": "Basic " + basic,
					"Content-Type": "application/x-www-form-urlencoded",
					"Accept": "application/json",
				},
				urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
				idempotent=True,
			)
		else:
			body = {
				"appName": c.app_name,
				"appVersion": c.app_version,
				"hostTenant": c.host_tenant or c.tenant,
				"userTenant": c.user_tenant or c.tenant,
			}
			response = self.send(
				"POST",
				self.url(TOKEN_MANAGER_PATH),
				{
					"X-SPACE-AUTH-KEY": f"{(c.token_manager_scheme or 'Basic').strip()} {basic}",
					"Content-Type": "application/json",
					"Accept": "application/json",
				},
				json.dumps(body).encode("utf-8"),
				idempotent=True,
			)
		if response.status != 200:
			raise error_from_response(response, "Insights Hub token request failed", write=False)
		data = response.json() or {}
		if not isinstance(data, dict) or not data.get("access_token"):
			raise InsightsHubError(
				"Insights Hub token response carries no access_token", status=response.status
			)
		self._token = (data["access_token"], time.time() + float(data.get("expires_in") or 300))
		return self._token[0]

	def headers(self, extra: dict | None = None) -> dict:
		headers = {"Accept": "application/json", "Authorization": "Bearer " + self.access_token()}
		headers.update(extra or {})
		return headers

	# Requests

	def send(
		self, method: str, url: str, headers: dict, body: bytes | None = None, *, idempotent: bool = False
	) -> Response:
		"""One HTTP call. Transport failures become transient errors; `idempotent` marks a request
		(a token fetch, a read, a time series upsert) whose loss cannot have left a half-done change."""
		try:
			return self.transport(method, url, headers, body, self.connection.timeout)
		except (OSError, TimeoutError) as e:
			raise InsightsHubError(
				f"Could not reach Insights Hub: {e}",
				transient=True,
				maybe_applied=method not in ("GET", "HEAD") and not idempotent,
			)

	def get(self, path: str, query: dict | None = None):
		"""GET a resource. Returns the decoded JSON, or None when Insights Hub answers 404."""
		response = self.send("GET", self.url(path, query), self.headers())
		if response.status == 404:
			return None
		if response.status >= 400:
			raise error_from_response(response, write=False)
		return response.json()

	def get_page(self, path: str, query: dict | None = None, size: int = 10, page: int = 0) -> list:
		"""One page of a collection, as a list, whatever envelope the service uses. A collection that
		answers 404 does not exist: that is a wrong service or resource path, not an empty result."""
		data = self.get(path, {**(query or {}), "page": str(page), "size": str(size)})
		if data is None:
			raise InsightsHubError(
				f"Insights Hub has no collection at {path}: check the service and resource of the mapping",
				status=404,
			)
		return items_of(data)

	def get_all(self, path: str, query: dict | None = None, size: int = 50, max_pages: int = 20):
		"""Every record of a collection, page by page, up to `max_pages`."""
		for page in range(max_pages):
			records = self.get_page(path, query, size=size, page=page)
			yield from records
			if len(records) < size:
				return

	def write(self, method: str, path: str, payload, *, idempotent: bool = False):
		"""PUT or POST a JSON body. Returns the decoded answer (None for 204 No Content)."""
		body = json.dumps(payload).encode("utf-8")
		headers = self.headers({"Content-Type": "application/json"})
		response = self.send(method, self.url(path), headers, body, idempotent=idempotent)
		if response.status >= 400:
			raise error_from_response(response, maybe_applied=not idempotent)
		return response.json() if response.body else None


def items_of(data) -> list:
	"""The list inside a collection answer: `_embedded.<anything>`, `content`, or the list itself."""
	if data is None:
		return []
	if isinstance(data, list):
		return data
	if not isinstance(data, dict):
		return []
	embedded = data.get("_embedded")
	if isinstance(embedded, dict):
		for value in embedded.values():
			if isinstance(value, list):
				return value
		return []
	for name in ("content", "items", "results", "data"):
		if isinstance(data.get(name), list):
			return data[name]
	return []


def error_from_response(
	response: Response,
	prefix: str = "Insights Hub rejected the request",
	*,
	write: bool = True,
	maybe_applied: bool | None = None,
) -> InsightsHubError:
	"""Read the platform's error body: `{"errors": [{"code", "message", "logref"}]}`.

	`write` is False for a read or a token fetch: a server error there cannot have changed anything."""
	code, message, details = None, "", []
	try:
		data = response.json()
		errors = data.get("errors") if isinstance(data, dict) else None
		if isinstance(errors, list) and errors:
			code = errors[0].get("code")
			message = errors[0].get("message") or ""
			details = [
				{"code": e.get("code"), "message": e.get("message"), "logref": e.get("logref")}
				for e in errors
				if isinstance(e, dict)
			]
		elif isinstance(data, dict) and data.get("message"):
			message = str(data["message"])
	except (ValueError, AttributeError):
		message = response.body[:500].decode("utf-8", "replace")
	status = response.status
	transient = status in TRANSIENT_STATUSES or status in AUTH_STATUSES
	text = f"{prefix} (HTTP {status}{', ' + code if code else ''})"
	if message:
		text += f": {message}"
	if maybe_applied is None:
		# A 5xx on a write may come after the write was applied.
		maybe_applied = write and status >= 500
	else:
		maybe_applied = maybe_applied and write and status >= 500
	return InsightsHubError(
		text, status=status, code=code, details=details, transient=transient, maybe_applied=maybe_applied
	)


def json_filter(filters: dict) -> str:
	"""The `filter` query value the platform APIs take: a compact JSON object."""
	return json.dumps(filters, separators=(",", ":"))
