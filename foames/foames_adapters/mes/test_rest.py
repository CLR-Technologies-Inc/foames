# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The shared REST client against the scripted fake: every authentication style, URL building with
{site}, collection envelopes and error bodies. No Frappe site needed."""

import base64
import unittest

from foames.foames_adapters.mes import rest
from foames.foames_adapters.mes.fake import FakeMES, mes_error, ok, token
from foames.foames_adapters.mes.rest import (
	AUTH_API_KEY,
	AUTH_BASIC,
	AUTH_BEARER,
	AUTH_NONE,
	AUTH_OAUTH,
	Connection,
	MESError,
	Response,
	RestClient,
	items_of,
)

BASE = "https://mes.example/api"


def client(fake=None, **overrides):
	connection = Connection(base_url=BASE, site="1010")
	for name, value in overrides.items():
		setattr(connection, name, value)
	return RestClient(connection, transport=fake or FakeMES())


class TestUrls(unittest.TestCase):
	def test_relative_and_absolute_paths(self):
		c = client()
		self.assertEqual(c.url("orders"), BASE + "/orders")
		self.assertEqual(c.url("/orders/"), BASE + "/orders/")
		self.assertEqual(c.url("https://other.example/x"), "https://other.example/x")

	def test_site_is_filled_in_paths_queries_and_headers(self):
		c = client(headers={"X-Customer": "{site}"}, site="a b")
		self.assertEqual(
			c.url("plants/{site}/orders", {"plant": "{site}", "n": None}),
			BASE + "/plants/a%20b/orders?plant=a%20b",
		)
		self.assertEqual(c.headers()["X-Customer"], "a b")

	def test_query_is_appended_to_a_path_that_has_one(self):
		self.assertEqual(client().url("orders?x=1", {"y": "2"}), BASE + "/orders?x=1&y=2")

	def test_odata_characters_stay_readable(self):
		url = client().url("Orders", {"$filter": "Order eq '1'", "$top": "2"})
		self.assertEqual(url, BASE + "/Orders?$filter=Order%20eq%20'1'&$top=2")


class TestAuth(unittest.TestCase):
	def test_none(self):
		self.assertNotIn("Authorization", client(auth=AUTH_NONE).headers())

	def test_basic(self):
		headers = client(auth=AUTH_BASIC, username="u", password="p").headers()
		self.assertEqual(headers["Authorization"], "Basic " + base64.b64encode(b"u:p").decode())

	def test_bearer(self):
		self.assertEqual(client(auth=AUTH_BEARER, token="tok").headers()["Authorization"], "Bearer tok")

	def test_api_key_header(self):
		headers = client(auth=AUTH_API_KEY, api_key="k", api_key_header="X-Plex-Connect-Api-Key").headers()
		self.assertEqual(headers["X-Plex-Connect-Api-Key"], "k")
		self.assertNotIn("Authorization", headers)
		self.assertEqual(
			client(auth=AUTH_API_KEY, api_key="k", api_key_header="").headers()["X-API-Key"], "k"
		)

	def test_oauth_client_credentials(self):
		fake = FakeMES().on("POST", "oauth/token", token("T9", 1799))
		c = client(
			fake,
			auth=AUTH_OAUTH,
			token_url="https://auth.example/oauth/token",
			client_id="id",
			client_secret="s",
			scope="read",
		)
		c.get("orders")
		c.get("orders")
		tokens = [r for r in fake.requests if "oauth/token" in r["path"]]
		self.assertEqual(len(tokens), 1)
		self.assertEqual(tokens[0]["headers"]["Authorization"], "Basic " + base64.b64encode(b"id:s").decode())
		self.assertEqual(tokens[0]["body"], b"grant_type=client_credentials&scope=read")
		self.assertEqual(fake.requests[-1]["headers"]["Authorization"], "Bearer T9")

	def test_oauth_needs_a_token_url_and_a_token(self):
		with self.assertRaises(MESError):
			client(auth=AUTH_OAUTH).access_token()
		fake = FakeMES().on("POST", "oauth/token", ok({"token_type": "bearer"}))
		with self.assertRaises(MESError):
			client(fake, auth=AUTH_OAUTH, token_url="https://auth.example/oauth/token").access_token()
		fake = FakeMES().on("POST", "oauth/token", mes_error(401, "bad client"))
		with self.assertRaises(MESError) as raised:
			client(fake, auth=AUTH_OAUTH, token_url="https://auth.example/oauth/token").access_token()
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)

	def test_extra_headers_come_before_auth(self):
		headers = client(
			auth=AUTH_BEARER, token="t", headers={"Accept": "application/xml", "X-Api-Version": "2"}
		).headers()
		self.assertEqual(
			(headers["Accept"], headers["X-Api-Version"], headers["Authorization"]),
			("application/xml", "2", "Bearer t"),
		)


class TestReads(unittest.TestCase):
	def test_get_and_404(self):
		fake = FakeMES().on("GET", "/orders/1", ok({"order": "1"}))
		c = client(fake)
		self.assertEqual(c.get("orders/1"), {"order": "1"})
		self.assertIsNone(c.get("orders/2"))

	def test_get_list_unwraps(self):
		fake = (
			FakeMES()
			.on("GET", "/odata", ok({"value": [{"a": 1}]}))
			.on("GET", "/v2", ok({"d": {"results": [{"b": 2}]}}))
			.on("GET", "/plain", ok([{"c": 3}]))
		)
		c = client(fake)
		self.assertEqual(c.get_list("odata"), [{"a": 1}])
		self.assertEqual(c.get_list("v2"), [{"b": 2}])
		self.assertEqual(c.get_list("plain"), [{"c": 3}])

	def test_items_of_every_envelope(self):
		self.assertEqual(items_of(None), [])
		self.assertEqual(items_of("x"), [])
		self.assertEqual(items_of({"_embedded": {"orders": [1]}}), [1])
		self.assertEqual(items_of({"_embedded": {}}), [])
		self.assertEqual(items_of({"content": [], "page": {}}), [])
		self.assertEqual(items_of({"records": [{"r": 1}]}), [{"r": 1}])
		# A filtered GET answered with the one record, unwrapped.
		self.assertEqual(items_of({"order": "1", "status": "ACTIVE"}), [{"order": "1", "status": "ACTIVE"}])
		self.assertEqual(items_of({}), [])
		self.assertEqual(items_of({"value": "scalar"}), [])
		self.assertEqual(items_of({"_links": {}}), [])

	def test_read_errors_never_count_as_applied(self):
		fake = FakeMES().on("GET", "/orders", mes_error(500, "boom"))
		with self.assertRaises(MESError) as raised:
			client(fake).get("orders")
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)


class TestWrites(unittest.TestCase):
	def test_post_json(self):
		fake = FakeMES().on("POST", "/orders", ok({"id": "o1"}, 201))
		self.assertEqual(client(fake).write("POST", "orders", {"a": 1})["id"], "o1")
		request = fake.requests[-1]
		self.assertEqual(
			(request["headers"]["Content-Type"], request["body"]), ("application/json", {"a": 1})
		)

	def test_no_body_and_non_json_answers(self):
		fake = (
			FakeMES()
			.on("POST", "/start", Response(200, {}, b"OK"))
			.on("DELETE", "/x", Response(204, {}, b""))
		)
		self.assertEqual(client(fake).write("POST", "start", None), {"_raw": "OK"})
		self.assertNotIn("Content-Type", fake.requests[-1]["headers"])
		self.assertIsNone(client(fake).write("DELETE", "x", None))

	def test_error_classes(self):
		for status, transient, applied in (
			(400, False, False),
			(409, False, False),
			(401, True, False),
			(429, True, False),
			(500, True, True),
			(503, True, True),
		):
			fake = FakeMES().on("POST", "/orders", mes_error(status, f"s{status}", code="C1"))
			with self.assertRaises(MESError) as raised:
				client(fake).write("POST", "orders", {})
			e = raised.exception
			self.assertEqual(
				(e.status, e.code, e.transient, e.maybe_applied),
				(status, "C1", transient, applied),
				msg=status,
			)
			self.assertIn(f"s{status}", str(e))

	def test_idempotent_write_server_error_needs_no_check(self):
		fake = FakeMES().on("PUT", "/orders", mes_error(502, "gateway"))
		with self.assertRaises(MESError) as raised:
			client(fake).write("PUT", "orders", {}, idempotent=True)
		self.assertFalse(raised.exception.maybe_applied)

	def test_network_failures(self):
		for error in (TimeoutError(), ConnectionResetError(), OSError("dns")):
			with self.assertRaises(MESError) as raised:
				client(FakeMES().on("POST", "/orders", error)).write("POST", "orders", {})
			self.assertTrue(raised.exception.transient and raised.exception.maybe_applied)
			with self.assertRaises(MESError) as raised:
				client(FakeMES().on("GET", "/orders", error)).get("orders")
			self.assertFalse(raised.exception.maybe_applied)


class TestErrorBodies(unittest.TestCase):
	def read(self, body, status=400):
		return rest.error_from_response(Response(status, {}, body))

	def test_variants(self):
		self.assertIn(
			"E1: first",
			str(self.read(b'{"errors": [{"code": "E1", "message": "first"}, {"code": "E2"}]}')).replace(
				", E1): first", "E1: first"
			),
		)
		e = self.read(b'{"errors": [{"code": "E1", "message": "first"}, {"code": "E2"}]}')
		self.assertEqual((e.code, len(e.details)), ("E1", 2))
		self.assertIn(
			"locked",
			str(self.read(b'{"error": {"code": "X", "message": {"lang": "en", "value": "Order locked"}}}')),
		)
		self.assertIn("plain", str(self.read(b'{"error": "plain"}')))
		self.assertIn("msg", str(self.read(b'{"Message": "msg"}')))
		self.assertIn("detail text", str(self.read(b'{"detail": "detail text", "title": "t"}')))
		self.assertIn("as text", str(self.read(b'"as text"')))
		self.assertIn("not json", str(self.read(b"not json")))
		self.assertIn("E9", str(self.read(b'[{"code": "E9", "title": "listed"}]')))
		self.assertEqual(str(self.read(b"", 500)), "The system rejected the request (HTTP 500)")
		self.assertEqual(str(self.read(b"{}", 500)), "The system rejected the request (HTTP 500)")


if __name__ == "__main__":
	unittest.main()
