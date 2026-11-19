# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Onshape connector's pure pieces: signatures, model parsing,
client error mapping and retries. The scripted fake stands in for Onshape; no
Frappe site and no credentials are needed for these."""

import base64
import hashlib
import hmac
import unittest

from foames.foames_adapters.onshape import auth, model
from foames.foames_adapters.onshape.client import (
	Connection,
	OnshapeAuthError,
	OnshapeClient,
	OnshapeError,
	OnshapeQuotaExceeded,
	OnshapeRateLimited,
	OnshapeUnavailable,
	error_from_response,
)
from foames.foames_adapters.onshape.fake import FakeOnshape


def expected_signature(secret: str, method: str, url: str, nonce: str, date: str, ctype: str) -> str:
	"""Independent re-implementation of the documented signed string, for cross-checking."""
	from urllib.parse import urlsplit

	parts = urlsplit(url)
	message = ("\n".join([method, nonce, date, ctype, parts.path, parts.query]) + "\n").lower().encode()
	return base64.b64encode(hmac.new(secret.encode(), message, hashlib.sha256).digest()).decode()


class AuthTests(unittest.TestCase):
	def test_headers_carry_signature_inputs(self):
		headers = auth.auth_headers(
			"GET", "https://cad.onshape.com/api/documents/d1?limit=5",
			"AK", "SK", nonce_value="n" * 25, date="Mon, 11 Apr 2016 20:08:56 GMT",
		)
		self.assertEqual(headers["On-Nonce"], "n" * 25)
		self.assertEqual(headers["Date"], "Mon, 11 Apr 2016 20:08:56 GMT")
		self.assertTrue(headers["Authorization"].startswith("On AK:HmacSHA256:"))

	def test_signature_matches_documented_scheme(self):
		url = "https://cad.onshape.com/api/documents/d1?ownerType=company"
		headers = auth.auth_headers("GET", url, "AK", "SK", nonce_value="N" * 25, date="D")
		sig = headers["Authorization"].split(":HmacSHA256:", 1)[1]
		self.assertEqual(sig, expected_signature("SK", "GET", url, "N" * 25, "D", "application/json"))

	def test_nonce_is_long_and_unique(self):
		a, b = auth.nonce(), auth.nonce()
		self.assertGreaterEqual(len(a), 16)
		self.assertNotEqual(a, b)


class ModelTests(unittest.TestCase):
	def test_pinned_only_for_version_and_microversion(self):
		for wvm, pinned in (("w", False), ("v", True), ("m", True)):
			ref = model.CadReference(kind="Document", document_id="d", wvm_type=wvm, wvm_id="x")
			self.assertEqual(ref.pinned, pinned)
			self.assertEqual(ref.mutable, wvm == "w")

	def test_workspace_label_is_unreleased(self):
		ref = model.CadReference(kind="Document", document_id="d", wvm_type="w", wvm_id="w1")
		self.assertEqual(ref.revision_label, "Unreleased workspace")

	def test_invalid_kind_and_wvm_rejected(self):
		with self.assertRaises(ValueError):
			model.CadReference(kind="Gadget", document_id="d", wvm_type="w", wvm_id="x")
		with self.assertRaises(ValueError):
			model.CadReference(kind="Document", document_id="d", wvm_type="z", wvm_id="x")
		with self.assertRaises(ValueError):
			model.CadReference(kind="Document", document_id="", wvm_type="w", wvm_id="x")

	def test_parse_document_prefers_microversion(self):
		ref = model.parse_document(
			{
				"id": "d1",
				"name": "Bracket",
				"defaultWorkspace": {"id": "w1"},
				"version": {"id": "v1"},
				"microversions": [{"id": "m9"}],
			}
		)
		self.assertEqual((ref.document_id, ref.wvm_type, ref.wvm_id), ("d1", "m", "m9"))
		self.assertTrue(ref.pinned)
		self.assertTrue(ref.canonical_url.endswith("/documents/d1/m/m9"))

	def test_parse_document_workspace_when_no_versions(self):
		ref = model.parse_document({"id": "d1", "name": "X", "defaultWorkspace": {"id": "w1"}})
		self.assertEqual((ref.wvm_type, ref.wvm_id), ("w", "w1"))
		self.assertFalse(ref.pinned)

	def test_parse_onshape_url_variants(self):
		parsed = model.parse_onshape_url("https://cad.onshape.com/documents/d1/w/w1/e/e2?x=1#frag")
		self.assertEqual(parsed, {"document_id": "d1", "wvm_type": "w", "wvm_id": "w1", "element_id": "e2"})
		self.assertIsNone(model.parse_onshape_url("https://cad.onshape.com/api/documents/d1"))
		self.assertIsNone(model.parse_onshape_url("not a url"))

	def test_bom_rows_keep_provenance_and_skip_idless(self):
		rows = model.parse_bom_rows(
			[
				{"partId": "p1", "name": "Bolt", "quantity": 4, "partNumber": "B-1"},
				{"name": "no id row"},
				{"part_id": "p2", "quantity": "2"},
			]
		)
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0]["part_id"], "p1")
		self.assertEqual(rows[0]["source"], "onshape")


class ClientTests(unittest.TestCase):
	def client(self, fake: FakeOnshape, **kw) -> OnshapeClient:
		values = {"base_url": "https://cad.onshape.com", "access_key": "AK", "secret_key": "SK"}
		values.update(kw)
		return OnshapeClient(Connection(**values), transport=fake, _sleep=lambda s: None)

	def test_get_document_round_trip(self):
		fake = FakeOnshape().document("d1", "Widget")
		ref = self.client(fake).document_reference("d1")
		self.assertEqual(ref.title, "Widget")
		self.assertEqual(ref.wvm_type, "w")
		self.assertEqual(fake.calls[0]["method"], "GET")
		self.assertIn("Authorization", fake.calls[0]["headers"])

	def test_writes_are_refused(self):
		fake = FakeOnshape()
		with self.assertRaises(OnshapeError):
			self.client(fake).request("POST", "/api/documents/d1")
		self.assertEqual(fake.calls, [])

	def test_auth_error_not_retried(self):
		fake = FakeOnshape()
		fake.add("GET", "/api/documents/d1", {"message": "bad key"}, status=403)
		with self.assertRaises(OnshapeAuthError):
			self.client(fake).get_document("d1")
		self.assertEqual(len(fake.calls), 1)

	def test_quota_exceeded_not_retried(self):
		fake = FakeOnshape()
		fake.add("GET", "/api/documents/d1", {"message": "quota"}, status=402)
		with self.assertRaises(OnshapeQuotaExceeded):
			self.client(fake).get_document("d1")
		self.assertEqual(len(fake.calls), 1)

	def test_rate_limit_retries_then_succeeds(self):
		fake = FakeOnshape().document("d1")
		calls = {"n": 0}

		def flaky(method, url, headers, body, timeout):
			calls["n"] += 1
			if calls["n"] == 1:
				return 429, {"Retry-After": "0"}, {"message": "slow down"}
			return fake(method, url, headers, body, timeout)

		client = OnshapeClient(
			Connection(base_url="https://cad.onshape.com", access_key="AK", secret_key="SK"),
			transport=flaky,
			_sleep=lambda s: None,
		)
		payload = client.get_document("d1")
		self.assertEqual(payload["id"], "d1")
		self.assertEqual(calls["n"], 2)

	def test_server_error_retries_then_fails(self):
		fake = FakeOnshape()
		fake.add("GET", "/api/documents/d1", {"message": "boom"}, status=500)
		with self.assertRaises(OnshapeUnavailable):
			self.client(fake, max_retries=2).get_document("d1")
		self.assertEqual(len(fake.calls), 3)  # initial + 2 retries

	def test_error_classification(self):
		self.assertIsInstance(error_from_response(401, {}), OnshapeAuthError)
		self.assertIsInstance(error_from_response(402, {}), OnshapeQuotaExceeded)
		self.assertIsInstance(error_from_response(429, {}, {"Retry-After": "3"}), OnshapeRateLimited)
		self.assertIsInstance(error_from_response(503, {}), OnshapeUnavailable)
		plain = error_from_response(404, {"message": "gone"})
		self.assertIsInstance(plain, OnshapeError)
		self.assertFalse(plain.retryable)


if __name__ == "__main__":
	unittest.main()
