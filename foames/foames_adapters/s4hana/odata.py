# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A small OData V2 client for S/4HANA's released APIs, using only the standard library.

It handles what S/4HANA requires of a caller: the `sap-client` parameter, Basic or OAuth 2.0
client-credentials authentication, and the CSRF token that every modifying request must carry
(fetched with `X-CSRF-Token: Fetch` and sent back together with the session cookies).

The HTTP call itself goes through a transport function, so tests can run without a server.
"""

import base64
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar


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


class ODataError(Exception):
	"""S/4HANA answered, or could not be reached.

	`transient` is True when trying again later may succeed (server errors, throttling, timeouts,
	network failures). Business rejections such as a closed posting period or a locked order are not
	transient: they need a person to fix the data first.

	`maybe_applied` is True when the request may have reached S/4HANA before the failure, so a
	retry must first check whether the posting already exists.
	"""

	def __init__(self, message, status=None, code=None, details=None, transient=False, maybe_applied=False):
		super().__init__(message)
		self.status = status
		self.code = code
		self.details = details or []
		self.transient = transient
		self.maybe_applied = maybe_applied


TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
# A rejected login cannot have applied a posting and clears up when the credentials are fixed, so
# the outbox retries it instead of failing the posting and holding its sequence group.
AUTH_STATUSES = {401, 403}


def urllib_transport(cookies: CookieJar, cafile: str | None = None):
	"""Default transport: urllib with a cookie jar, so the CSRF token and session stay paired."""
	context = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
	opener = urllib.request.build_opener(
		urllib.request.HTTPCookieProcessor(cookies), urllib.request.HTTPSHandler(context=context)
	)

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
	"""Where and how to reach one S/4HANA system."""

	base_url: str
	client: str = ""
	auth: str = "Basic"  # "Basic" or "OAuth 2.0 Client Credentials"
	username: str = ""
	password: str = ""
	token_url: str = ""
	client_id: str = ""
	client_secret: str = ""
	scope: str = ""
	language: str = "EN"
	timeout: float = 30.0
	cafile: str | None = None
	service_root: str = "/sap/opu/odata/sap/"
	extra: dict = field(default_factory=dict)


class ODataClient:
	def __init__(self, connection: Connection, transport=None):
		self.connection = connection
		self.cookies = CookieJar()
		self.transport = transport or urllib_transport(self.cookies, connection.cafile)
		self._csrf: dict[str, str] = {}
		self._token: tuple[str, float] | None = None

	# URLs

	def service_url(self, service: str) -> str:
		root = self.connection.base_url.rstrip("/") + "/" + self.connection.service_root.strip("/") + "/"
		return root + service.strip("/") + "/"

	def url(self, service: str, path: str = "", query: dict | None = None) -> str:
		query = dict(query or {})
		if self.connection.client:
			query["sap-client"] = self.connection.client
		url = self.service_url(service) + path
		if query:
			url += "?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote, safe="$,'()=")
		return url

	# Authentication

	def auth_header(self) -> str:
		c = self.connection
		if c.auth == "OAuth 2.0 Client Credentials":
			return "Bearer " + self.access_token()
		raw = f"{c.username}:{c.password}".encode()
		return "Basic " + base64.b64encode(raw).decode("ascii")

	def access_token(self) -> str:
		if self._token and self._token[1] > time.time() + 30:
			return self._token[0]
		c = self.connection
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
			raise ODataError(
				f"OAuth token request failed with HTTP {response.status}",
				status=response.status,
				transient=response.status in TRANSIENT_STATUSES,
			)
		data = response.json() or {}
		self._token = (data["access_token"], time.time() + float(data.get("expires_in") or 300))
		return self._token[0]

	def headers(self, extra: dict | None = None) -> dict:
		headers = {"Accept": "application/json", "Authorization": self.auth_header()}
		if self.connection.language:
			headers["Accept-Language"] = self.connection.language.lower()
		headers.update(extra or {})
		return headers

	# Requests

	def send(
		self, method: str, url: str, headers: dict, body: bytes | None = None, *, idempotent: bool = False
	) -> Response:
		"""One HTTP call. Transport failures become transient ODataErrors; `idempotent` marks a request
		(a token fetch, a read) whose loss cannot have changed anything in S/4HANA."""
		try:
			return self.transport(method, url, headers, body, self.connection.timeout)
		except (OSError, TimeoutError) as e:
			# Connection refused or reset, DNS failure, timeout. For a write we cannot tell whether
			# S/4HANA received it.
			raise ODataError(
				f"Could not reach S/4HANA: {e}",
				transient=True,
				maybe_applied=method not in ("GET", "HEAD") and not idempotent,
			)

	def get(self, service: str, path: str = "", query: dict | None = None) -> dict | None:
		"""GET an entity or collection. Returns the `d` payload, or None when S/4HANA answers 404."""
		query = {"$format": "json", **(query or {})}
		response = self.send("GET", self.url(service, path, query), self.headers())
		if response.status == 404:
			return None
		if response.status >= 400:
			raise error_from_response(response)
		data = response.json() or {}
		return data.get("d", data)

	def get_entity(self, service: str, entity_set: str, keys: dict, query: dict | None = None) -> dict | None:
		return self.get(service, entity_set + key_predicate(keys), query)

	def query(self, service: str, entity_set: str, filters: dict, top: int = 10, select=None) -> list[dict]:
		query = {"$filter": filter_expression(filters), "$top": str(top)}
		if select:
			query["$select"] = ",".join(select)
		data = self.get(service, entity_set, query) or {}
		return data.get("results", [])

	def csrf_token(self, service: str, refresh: bool = False) -> str:
		if refresh or service not in self._csrf:
			response = self.send("GET", self.url(service), self.headers({"X-CSRF-Token": "Fetch"}))
			token = response.header("x-csrf-token")
			if response.status >= 400 or not token:
				raise error_from_response(response, "Could not fetch a CSRF token from S/4HANA")
			self._csrf[service] = token
		return self._csrf[service]

	def post(self, service: str, entity_set: str, payload: dict) -> dict:
		"""Create an entity (deep inserts included). Fetches a CSRF token first and refreshes it once
		when S/4HANA says it expired."""
		body = json.dumps(payload).encode("utf-8")
		url = self.url(service, entity_set)
		for attempt in range(2):
			headers = self.headers(
				{
					"Content-Type": "application/json",
					"X-CSRF-Token": self.csrf_token(service, refresh=attempt > 0),
				}
			)
			response = self.send("POST", url, headers, body)
			token_required = (
				response.status == 403 and (response.header("x-csrf-token") or "").lower() == "required"
			)
			if not token_required:
				break
		if response.status >= 400:
			raise error_from_response(response)
		data = response.json() or {}
		return data.get("d", data)


def error_from_response(response: Response, prefix: str = "S/4HANA rejected the request") -> ODataError:
	"""Read SAP's error body ({"error": {"code", "message": {"value"}, "innererror": ...}})."""
	code, message, details = None, "", []
	try:
		error = (response.json() or {}).get("error", {})
		code = error.get("code")
		message = (error.get("message") or {}).get("value", "")
		for detail in (error.get("innererror") or {}).get("errordetails", []):
			details.append({"code": detail.get("code"), "message": detail.get("message")})
	except (ValueError, AttributeError):
		message = response.body[:500].decode("utf-8", "replace")
	status = response.status
	transient = status in TRANSIENT_STATUSES or status in AUTH_STATUSES
	text = f"{prefix} (HTTP {status}{', ' + code if code else ''})"
	if message:
		text += f": {message}"
	# A 5xx on a write may come after the posting was committed.
	return ODataError(
		text, status=status, code=code, details=details, transient=transient, maybe_applied=status >= 500
	)


def literal(value) -> str:
	"""An OData V2 literal. Strings are quoted with embedded quotes doubled."""
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, int | float):
		return str(value)
	return "'" + str(value).replace("'", "''") + "'"


def key_predicate(keys: dict) -> str:
	"""`('X')` for one key, `(A='X',B='Y')` for a composite key, each value URL-encoded."""
	if len(keys) == 1:
		return "(" + urllib.parse.quote(literal(next(iter(keys.values()))), safe="'") + ")"
	parts = [name + "=" + urllib.parse.quote(literal(value), safe="'") for name, value in keys.items()]
	return "(" + ",".join(parts) + ")"


def filter_expression(filters: dict) -> str:
	return " and ".join(f"{name} eq {literal(value)}" for name, value in filters.items())
