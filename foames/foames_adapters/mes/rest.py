# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A JSON REST client for the MES and MOM systems FoaMES talks to, using only the standard library.

The systems differ in how a caller logs in, so the connection names one of these styles:

- **None**: an open endpoint, or one guarded by the network.
- **Basic**: user name and password (Tulip's API credentials, an on-premise MES user).
- **Bearer Token**: a long-lived token issued by the system, sent as `Authorization: Bearer`.
- **API Key Header**: a key in a header the system names (Plex's `X-Plex-Connect-Api-Key`).
- **OAuth 2.0 Client Credentials**: a client id and secret exchanged at a token URL for a bearer
  token (SAP Digital Manufacturing through XSUAA, Proficy through UAA).

Any extra headers the system needs on every call (a customer or tenant id, an API version) come
with the connection. The HTTP call itself goes through a transport function, so tests can run
without a system.
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


class MESError(Exception):
	"""The system answered with an error, or could not be reached.

	`transient` is True when trying again later may succeed (server errors, throttling, timeouts,
	network failures, a rejected login). Validation errors and business rejections are not: they need
	a person to fix the data.

	`maybe_applied` is True when a write may have reached the system before the failure, so a retry
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

AUTH_NONE = "None"
AUTH_BASIC = "Basic"
AUTH_BEARER = "Bearer Token"
AUTH_API_KEY = "API Key Header"
AUTH_OAUTH = "OAuth 2.0 Client Credentials"
AUTH_METHODS = (AUTH_NONE, AUTH_BASIC, AUTH_BEARER, AUTH_API_KEY, AUTH_OAUTH)


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
	"""Where and how to reach one system."""

	base_url: str
	auth: str = AUTH_NONE
	username: str = ""
	password: str = ""
	token: str = ""  # Bearer Token
	api_key: str = ""  # API Key Header
	api_key_header: str = "X-API-Key"
	token_url: str = ""  # OAuth 2.0
	client_id: str = ""
	client_secret: str = ""
	scope: str = ""
	# A site, plant or tenant id the system wants in paths and queries, available as {site}.
	site: str = ""
	headers: dict = field(default_factory=dict)
	timeout: float = 30.0
	cafile: str | None = None

	def fill(self, text: str, quote: bool = False) -> str:
		"""`{site}` in a path, query value or header becomes the connection's site; `quote` URL-encodes
		it, for a path (query values are encoded with the rest of the query)."""
		site = urllib.parse.quote(self.site or "", safe="") if quote else (self.site or "")
		return (text or "").replace("{site}", site)


class RestClient:
	def __init__(self, connection: Connection, transport=None):
		self.connection = connection
		self.transport = transport or urllib_transport(connection.cafile)
		self._token: tuple[str, float] | None = None

	# URLs

	def url(self, path: str, query: dict | None = None) -> str:
		"""`<base>/<path>`, with `{site}` filled in and the query values URL-encoded. A path that is
		already absolute is used as it is."""
		path = self.connection.fill(path, quote=True)
		if path.startswith("http://") or path.startswith("https://"):
			url = path
		else:
			url = self.connection.base_url.rstrip("/") + "/" + path.lstrip("/")
		if query:
			pairs = [(k, self.connection.fill(str(v))) for k, v in query.items() if v is not None]
			url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
				pairs, quote_via=urllib.parse.quote, safe="$,'()="
			)
		return url

	# Authentication

	def auth_headers(self) -> dict:
		c = self.connection
		if c.auth == AUTH_BASIC:
			raw = f"{c.username}:{c.password}".encode()
			return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
		if c.auth == AUTH_BEARER:
			return {"Authorization": "Bearer " + c.token}
		if c.auth == AUTH_API_KEY:
			return {c.api_key_header or "X-API-Key": c.api_key}
		if c.auth == AUTH_OAUTH:
			return {"Authorization": "Bearer " + self.access_token()}
		return {}

	def access_token(self) -> str:
		if self._token and self._token[1] > time.time() + 30:
			return self._token[0]
		c = self.connection
		if not c.token_url:
			raise MESError("OAuth 2.0 client credentials need a token URL")
		form = {"grant_type": "client_credentials"}
		if c.scope:
			form["scope"] = c.scope
		basic = base64.b64encode(f"{c.client_id}:{c.client_secret}".encode()).decode("ascii")
		response = self.send(
			"POST",
			c.token_url,
			{
				"Authorization": "Basic " + basic,
				"Content-Type": "application/x-www-form-urlencoded",
				"Accept": "application/json",
			},
			urllib.parse.urlencode(form).encode(),
			idempotent=True,
		)
		if response.status != 200:
			raise error_from_response(response, "OAuth token request failed", write=False)
		data = response.json() or {}
		if not isinstance(data, dict) or not data.get("access_token"):
			raise MESError("OAuth token response carries no access_token", status=response.status)
		self._token = (data["access_token"], time.time() + float(data.get("expires_in") or 300))
		return self._token[0]

	def headers(self, extra: dict | None = None) -> dict:
		headers = {"Accept": "application/json"}
		headers.update({k: self.connection.fill(v) for k, v in (self.connection.headers or {}).items()})
		headers.update(self.auth_headers())
		headers.update(extra or {})
		return headers

	# Requests

	def send(
		self, method: str, url: str, headers: dict, body: bytes | None = None, *, idempotent: bool = False
	) -> Response:
		"""One HTTP call. Transport failures become transient errors; `idempotent` marks a request
		(a token fetch, a read, an upsert) whose loss cannot have left a half-done change."""
		try:
			return self.transport(method, url, headers, body, self.connection.timeout)
		except (OSError, TimeoutError) as e:
			raise MESError(
				f"Could not reach the system: {e}",
				transient=True,
				maybe_applied=method not in ("GET", "HEAD") and not idempotent,
			)

	def get(self, path: str, query: dict | None = None):
		"""GET a resource. Returns the decoded JSON, or None when the system answers 404."""
		response = self.send("GET", self.url(path, query), self.headers())
		if response.status == 404:
			return None
		if response.status >= 400:
			raise error_from_response(response, write=False)
		return response.json()

	def get_list(self, path: str, query: dict | None = None) -> list:
		"""GET a collection, as a list, whatever envelope the system uses."""
		return items_of(self.get(path, query))

	def write(self, method: str, path: str, payload, *, idempotent: bool = False):
		"""PUT, POST or PATCH a JSON body. Returns the decoded answer (None for an empty body)."""
		body = json.dumps(payload).encode("utf-8") if payload is not None else None
		headers = self.headers({"Content-Type": "application/json"} if body is not None else {})
		response = self.send(method, self.url(path), headers, body, idempotent=idempotent)
		if response.status >= 400:
			raise error_from_response(response, maybe_applied=not idempotent)
		try:
			return response.json() if response.body else None
		except ValueError:
			return {"_raw": response.body[:500].decode("utf-8", "replace")}


ENVELOPE_KEYS = ("value", "results", "content", "items", "data", "records", "Items", "Data")


def items_of(data) -> list:
	"""The list inside a collection answer: the list itself, OData's `value` or `d.results`,
	`_embedded.<anything>`, `content`, `items`, `results`, `data` or `records`. A single record
	that is not wrapped at all (some APIs answer a filtered GET with the one record) is a list of one."""
	if data is None:
		return []
	if isinstance(data, list):
		return data
	if not isinstance(data, dict):
		return []
	if isinstance(data.get("d"), dict):
		return items_of(data["d"])
	embedded = data.get("_embedded")
	if isinstance(embedded, dict):
		for value in embedded.values():
			if isinstance(value, list):
				return value
		return []
	for name in ENVELOPE_KEYS:
		if isinstance(data.get(name), list):
			return data[name]
	if any(name in data for name in ENVELOPE_KEYS) or "page" in data or "_links" in data:
		return []
	return [data] if data else []


def error_from_response(
	response: Response,
	prefix: str = "The system rejected the request",
	*,
	write: bool = True,
	maybe_applied: bool | None = None,
) -> MESError:
	"""Read whatever error body the system sends: `{"errors": [...]}`, `{"error": {"code",
	"message"}}` (also OData's `message.value`), `{"message"}`, `{"detail"}` or `{"title"}`.

	`write` is False for a read or a token fetch: a server error there cannot have changed anything."""
	code, message, details = None, "", []
	try:
		data = response.json()
		if isinstance(data, dict):
			code, message, details = _read_error(data)
		elif isinstance(data, list) and data and isinstance(data[0], dict):
			code, message, details = _read_error({"errors": data})
		elif isinstance(data, str):
			message = data
	except (ValueError, AttributeError):
		message = response.body[:500].decode("utf-8", "replace")
	status = response.status
	transient = status in TRANSIENT_STATUSES or status in AUTH_STATUSES
	text = f"{prefix} (HTTP {status}{', ' + str(code) if code else ''})"
	if message:
		text += f": {message}"
	if maybe_applied is None:
		# A 5xx on a write may come after the write was applied.
		maybe_applied = write and status >= 500
	else:
		maybe_applied = maybe_applied and write and status >= 500
	return MESError(
		text, status=status, code=code, details=details, transient=transient, maybe_applied=maybe_applied
	)


def _read_error(data: dict) -> tuple:
	errors = data.get("errors")
	if isinstance(errors, list) and errors and isinstance(errors[0], dict):
		first = errors[0]
		details = [e for e in errors if isinstance(e, dict)]
		return (
			first.get("code"),
			_text(first.get("message") or first.get("detail") or first.get("title")),
			details,
		)
	error = data.get("error")
	if isinstance(error, dict):
		return error.get("code"), _text(error.get("message") or error.get("description")), [error]
	if isinstance(error, str):
		return data.get("code"), error, []
	for name in ("message", "Message", "detail", "title", "error_description", "errorMessage"):
		if data.get(name):
			return data.get("code") or data.get("errorCode"), _text(data[name]), [data]
	return data.get("code"), "", [data] if data else []


def _text(value) -> str:
	if isinstance(value, dict):  # OData V2: {"lang": "en", "value": "..."}
		return str(value.get("value") or value.get("text") or "")
	return str(value or "")


def odata_literal(value) -> str:
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, int | float):
		return str(value)
	return "'" + str(value).replace("'", "''") + "'"


def json_filter(filters: dict) -> str:
	return json.dumps(filters, separators=(",", ":"))
