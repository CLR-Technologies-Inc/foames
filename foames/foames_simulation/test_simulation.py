# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Frappe-side simulation client and lifecycle mirror. No site needed."""

import json
import unittest

from foames.foames_simulation.client import ProviderClient, ProviderError
from foames.foames_simulation.simulation import (
	TransitionError,
	epoch_to_datetime,
	evidence_status,
	is_terminal,
	transition,
)


def fake_transport(routes):
	"""routes: {(method, path): (status, payload)} — path matched without query."""

	def transport(method, url, headers, body, timeout):
		from urllib.parse import urlsplit

		key = (method, urlsplit(url).path)
		entry = routes.get(key)
		if entry is None:
			return 404, {}, {"error": "not found"}
		status, payload = entry
		return status, {"Content-Type": "application/json"}, json.dumps(payload).encode()

	return transport


class ClientTests(unittest.TestCase):
	def client(self, routes, **kw):
		values = {"base_url": "http://worker:8765", "token": "t0k", "timeout": 5}
		values.update(kw)
		return ProviderClient(transport=fake_transport(routes), **values)

	def test_health_and_cases(self):
		client = self.client({
			("GET", "/health"): (200, {"ok": True}),
			("GET", "/cases"): (200, {"ok": True, "cases": [{"name": "pitzdaily"}]}),
		})
		self.assertTrue(client.health()["ok"])
		self.assertEqual(client.cases()[0]["name"], "pitzdaily")

	def test_submit_sends_manifest_and_requester(self):
		seen = {}

		def transport(method, url, headers, body, timeout):
			seen["body"] = json.loads(body.decode())
			seen["auth"] = headers.get("Authorization")
			return 202, {"Content-Type": "application/json"}, json.dumps({"ok": True, "run": {"run_id": "r1", "status": "queued"}}).encode()

		client = ProviderClient("http://w:1", token="sekrit", transport=transport)
		response = client.submit({"case": "pitzdaily", "params": {}}, requester="eng@x")
		self.assertEqual(response["run"]["run_id"], "r1")
		self.assertEqual(seen["body"]["requester"], "eng@x")
		self.assertEqual(seen["auth"], "Bearer sekrit")

	def test_auth_failure_is_not_retryable(self):
		client = self.client({("GET", "/cases"): (401, {"error": "unauthorized"})})
		with self.assertRaises(ProviderError) as ctx:
			client.cases()
		self.assertFalse(ctx.exception.retryable)

	def test_server_error_retryable(self):
		client = self.client({("GET", "/cases"): (503, {"error": "boom"})})
		with self.assertRaises(ProviderError) as ctx:
			client.cases()
		self.assertTrue(ctx.exception.retryable)

	def test_bad_manifest_is_client_error(self):
		client = self.client({("POST", "/runs"): (400, {"error": "unknown case"})})
		with self.assertRaises(ProviderError) as ctx:
			client.submit({"case": "nope"})
		self.assertEqual(ctx.exception.status, 400)


class LifecycleTests(unittest.TestCase):
	def test_transitions(self):
		self.assertEqual(transition("queued", "running"), "running")
		self.assertEqual(transition("running", "succeeded"), "succeeded")
		with self.assertRaises(TransitionError):
			transition("succeeded", "running")

	def test_terminal_and_evidence(self):
		self.assertTrue(is_terminal("timed_out"))
		self.assertEqual(evidence_status("succeeded"), "Candidate")
		self.assertEqual(evidence_status("failed"), "Not evidence")

	def test_epoch_conversion(self):
		self.assertIsNone(epoch_to_datetime(None))
		self.assertIsNotNone(epoch_to_datetime(1730000000))
		self.assertIsNone(epoch_to_datetime("not a time"))


if __name__ == "__main__":
	unittest.main()
