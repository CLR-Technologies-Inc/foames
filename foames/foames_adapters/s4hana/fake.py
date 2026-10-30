# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A scripted stand-in for S/4HANA's HTTP interface, used by the tests."""

import json
import urllib.parse

from foames.foames_adapters.s4hana.odata import Response


class FakeS4HANA:
	"""Answers requests from a list of (method, path fragment, response) rules, first match wins.

	A CSRF token fetch is matched as method "FETCH". A rule's response may be a Response, an exception to raise, or a callable taking the request.
	Rules marked `once` are dropped after their first use. Every request is recorded in `requests`.
	"""

	def __init__(self):
		self.rules = []
		self.requests = []

	def on(self, method, fragment, response, once=False):
		self.rules.append([method, fragment, response, once])
		return self

	def __call__(self, method, url, headers, body, timeout):
		parsed = urllib.parse.urlsplit(url)
		request = {
			"method": method,
			"url": url,
			"path": urllib.parse.unquote(parsed.path),
			"query": dict(urllib.parse.parse_qsl(parsed.query)),
			"headers": headers,
			"body": json.loads(body) if body and headers.get("Content-Type") == "application/json" else body,
		}
		self.requests.append(request)
		effective = "FETCH" if headers.get("X-CSRF-Token") == "Fetch" else method
		for rule in self.rules:
			rule_method, fragment, response, once = rule
			if rule_method == effective and fragment in request["path"]:
				if once:
					self.rules.remove(rule)
				if isinstance(response, Exception):
					raise response
				if callable(response):
					return response(request)
				return response
		return Response(404, {}, b"")


def ok(data, status=200, headers=None):
	return Response(status, headers or {}, json.dumps({"d": data}).encode())


def sap_error(status, code, message):
	body = {"error": {"code": code, "message": {"lang": "en", "value": message}}}
	return Response(status, {}, json.dumps(body).encode())


def csrf(token="T1"):
	return Response(200, {"x-csrf-token": token}, b"")
