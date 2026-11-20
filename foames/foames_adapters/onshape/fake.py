# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A scripted stand-in for Onshape's HTTP API, used by the tests. No network, no credentials."""

from __future__ import annotations

import json


class FakeOnshape:
	"""Answers GET requests from a route table; records every call for assertions."""

	def __init__(self, routes: dict | None = None):
		# routes: {"GET /api/documents/d1": payload-or-(status, payload, headers)}
		self.routes = routes or {}
		self.calls: list[dict] = []

	def add(self, method: str, path: str, payload, status: int = 200, headers: dict | None = None):
		self.routes["{0} {1}".format(method, path)] = (status, payload, headers or {})

	def document(self, did: str, name: str = "Widget", workspace: str = "w1", version: str = "v1"):
		self.add(
			"GET",
			"/api/documents/" + did,
			{
				"id": did,
				"name": name,
				"defaultWorkspace": {"id": workspace, "name": "Main"},
				"version": {"id": version, "name": "V1"},
			},
		)
		return self

	@staticmethod
	def _key(method: str, url: str) -> str:
		path = url.split("?", 1)[0]
		return "{0} {1}".format(method, path)

	def __call__(self, method: str, url: str, headers: dict, body, timeout: float):
		self.calls.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout})
		entry = self.routes.get(self._key(method, url))
		if entry is None:
			# Try the path without query already handled; report a 404 JSON error.
			return 404, {}, {"message": "Not found: " + url}
		status, payload, headers = entry
		return status, headers, payload
