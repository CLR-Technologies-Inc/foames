# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A scripted stand-in for an MES's HTTP interface, used by the tests."""

import json
import urllib.parse

from foames.foames_adapters.mes.rest import Response


class FakeMES:
	"""Answers requests from a list of (method, path fragment, response) rules, first match wins.

	A rule's response may be a Response, an exception to raise, or a callable taking the request.
	Rules marked `once` are dropped after their first use. Every request is recorded in `requests`.
	A token request is answered with a bearer token unless a rule for "oauth/token" says otherwise.
	"""

	def __init__(self):
		self.rules = []
		self.requests = []

	def on(self, method, fragment, response, once=False):
		self.rules.append([method, fragment, response, once])
		return self

	def __call__(self, method, url, headers, body, timeout):
		parsed = urllib.parse.urlsplit(url)
		query = dict(urllib.parse.parse_qsl(parsed.query))
		if "filter" in query:
			try:
				query["filter"] = json.loads(query["filter"])
			except ValueError:
				pass
		is_json = (headers.get("Content-Type") or "").startswith("application/json")
		request = {
			"method": method,
			"url": url,
			"path": urllib.parse.unquote(parsed.path),
			"query": query,
			"headers": headers,
			"body": json.loads(body) if body and is_json else body,
		}
		self.requests.append(request)
		for rule in self.rules:
			rule_method, fragment, response, once = rule
			if rule_method == method and fragment in request["path"]:
				if once:
					self.rules.remove(rule)
				if isinstance(response, Exception):
					raise response
				if callable(response):
					return response(request)
				return response
		if "oauth/token" in request["path"]:
			return token()
		return Response(404, {}, b"")


def ok(data, status=200, headers=None):
	return Response(status, headers or {}, json.dumps(data).encode())


def no_content():
	return Response(204, {}, b"")


def mes_error(status, message, code=None):
	body = {"error": {"code": code or "E", "message": message}}
	return Response(status, {}, json.dumps(body).encode())


def token(value="T1", expires_in=1799):
	return ok({"access_token": value, "token_type": "bearer", "expires_in": expires_in})
