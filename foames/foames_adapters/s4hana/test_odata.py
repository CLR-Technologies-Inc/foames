# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The OData client piece by piece: URLs, headers, authentication, CSRF handling, error mapping and
literals. The scripted fake answers every HTTP call. No Frappe site needed."""

import base64
import json
import time
import unittest
from unittest.mock import patch

from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.foames_adapters.s4hana.odata import (
	AUTH_STATUSES,
	TRANSIENT_STATUSES,
	Connection,
	ODataClient,
	ODataError,
	Response,
	error_from_response,
	filter_expression,
	key_predicate,
	literal,
)


def client(fake=None, **kw):
	values = {"base_url": "https://s4.example.com:44300", "client": "100", "username": "U", "password": "P"}
	values.update(kw)
	return ODataClient(Connection(**values), transport=fake or FakeS4HANA())


class TestResponse(unittest.TestCase):
	def test_header_lookup_ignores_case(self):
		response = Response(200, {"X-CSRF-Token": "abc", "content-type": "x"})
		self.assertEqual(response.header("x-csrf-token"), "abc")
		self.assertEqual(response.header("CONTENT-TYPE"), "x")
		self.assertIsNone(response.header("missing"))

	def test_json_of_empty_body_is_none(self):
		self.assertIsNone(Response(204, {}).json())
		self.assertEqual(Response(200, {}, b'{"a": 1}').json(), {"a": 1})


class TestURLs(unittest.TestCase):
	def test_service_url_normalises_slashes(self):
		c = client(base_url="https://s4.example.com/")
		self.assertEqual(
			c.service_url("/API_PRODUCT_SRV/"), "https://s4.example.com/sap/opu/odata/sap/API_PRODUCT_SRV/"
		)

	def test_custom_service_root(self):
		c = client(service_root="odata/v2")
		self.assertEqual(c.service_url("S"), "https://s4.example.com:44300/odata/v2/S/")

	def test_url_without_client_or_query(self):
		c = client(client="")
		self.assertEqual(
			c.url("S", "A_Product('1')"), "https://s4.example.com:44300/sap/opu/odata/sap/S/A_Product('1')"
		)

	def test_url_encodes_query_but_keeps_odata_characters(self):
		url = client().url("S", "E", {"$filter": "Name eq 'a b'", "$expand": "to_Description"})
		self.assertIn("$filter=Name%20eq%20'a%20b'", url)
		self.assertIn("$expand=to_Description", url)
		self.assertIn("sap-client=100", url)

	def test_url_does_not_mutate_the_query_dict(self):
		query = {"$top": "1"}
		client().url("S", "E", query)
		self.assertEqual(query, {"$top": "1"})


class TestHeaders(unittest.TestCase):
	def test_basic_auth_header(self):
		expected = "Basic " + base64.b64encode(b"U:P").decode()
		self.assertEqual(client().auth_header(), expected)

	def test_accept_language_is_lowercased_and_optional(self):
		self.assertEqual(client(language="DE").headers()["Accept-Language"], "de")
		self.assertNotIn("Accept-Language", client(language="").headers())

	def test_extra_headers_override_defaults(self):
		headers = client().headers({"Accept": "application/xml", "X-Extra": "1"})
		self.assertEqual((headers["Accept"], headers["X-Extra"]), ("application/xml", "1"))
		self.assertIn("Authorization", headers)


class TestOAuth(unittest.TestCase):
	def oauth_client(self, fake, **kw):
		return client(
			fake,
			auth="OAuth 2.0 Client Credentials",
			token_url="https://auth.example.com/oauth/token",
			client_id="id",
			client_secret="secret",
			**kw,
		)

	def token(self, **data):
		data.setdefault("access_token", "abc")
		return Response(200, {}, json.dumps(data).encode())

	def test_token_request_form_and_credentials(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", self.token())
		self.oauth_client(fake, scope="API_PRODUCT_SRV").access_token()
		request = fake.requests[0]
		self.assertEqual(
			request["headers"]["Authorization"], "Basic " + base64.b64encode(b"id:secret").decode()
		)
		self.assertEqual(request["headers"]["Content-Type"], "application/x-www-form-urlencoded")
		self.assertEqual(request["body"], b"grant_type=client_credentials&scope=API_PRODUCT_SRV")

	def test_scope_is_omitted_when_empty(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", self.token())
		self.oauth_client(fake).access_token()
		self.assertEqual(fake.requests[0]["body"], b"grant_type=client_credentials")

	def test_token_is_refreshed_shortly_before_expiry(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", self.token(expires_in=20))
		c = self.oauth_client(fake)
		c.access_token()
		c.access_token()  # 20 s minus the 30 s margin: already due
		self.assertEqual(len(fake.requests), 2)

	def test_token_is_cached_until_near_expiry(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", self.token(expires_in=3600))
		c = self.oauth_client(fake)
		c.access_token()
		with patch("foames.foames_adapters.s4hana.odata.time.time", return_value=time.time() + 3600 - 31):
			c.access_token()
		with patch("foames.foames_adapters.s4hana.odata.time.time", return_value=time.time() + 3600 - 29):
			c.access_token()
		self.assertEqual(len(fake.requests), 2)

	def test_missing_expires_in_defaults(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", self.token())
		c = self.oauth_client(fake)
		c.access_token()
		self.assertGreater(c._token[1], time.time() + 200)

	def test_token_failures(self):
		# A rejected login is transient for the outbox: it clears up when the credentials are fixed.
		for status, transient in ((401, True), (400, False), (503, True)):
			fake = FakeS4HANA().on("POST", "/oauth/token", Response(status, {}, b""))
			with self.assertRaises(ODataError) as raised:
				self.oauth_client(fake).access_token()
			self.assertEqual(raised.exception.status, status)
			self.assertEqual(raised.exception.transient, transient)
			self.assertFalse(raised.exception.maybe_applied)

	def test_token_response_without_a_token(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", Response(200, {}, b'{"error": "x"}'))
		with self.assertRaises(ODataError):
			self.oauth_client(fake).access_token()
		fake = FakeS4HANA().on("POST", "/oauth/token", Response(200, {}, b"[]"))
		with self.assertRaises(ODataError):
			self.oauth_client(fake).access_token()

	def test_token_network_failure_is_transient_and_not_applied(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", ConnectionResetError("reset"))
		with self.assertRaises(ODataError) as raised:
			self.oauth_client(fake).access_token()
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)

	def test_bearer_header_on_requests(self):
		fake = FakeS4HANA().on("POST", "/oauth/token", self.token()).on("GET", "E", ok({}))
		self.oauth_client(fake).get("S", "E")
		self.assertEqual(fake.requests[-1]["headers"]["Authorization"], "Bearer abc")


class TestSend(unittest.TestCase):
	def test_os_error_on_read_is_transient_and_not_applied(self):
		fake = FakeS4HANA().on("GET", "E", OSError("dns"))
		with self.assertRaises(ODataError) as raised:
			client(fake).get("S", "E")
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)
		self.assertIn("Could not reach S/4HANA", str(raised.exception))

	def test_timeout_on_write_may_have_been_applied(self):
		fake = FakeS4HANA().on("FETCH", "S", csrf()).on("POST", "E", TimeoutError())
		with self.assertRaises(ODataError) as raised:
			client(fake).post("S", "E", {})
		self.assertTrue(raised.exception.maybe_applied)

	def test_idempotent_write_is_not_applied(self):
		fake = FakeS4HANA().on("POST", "x", OSError())
		with self.assertRaises(ODataError) as raised:
			client(fake).send("POST", "https://s4/x", {}, b"", idempotent=True)
		self.assertFalse(raised.exception.maybe_applied)

	def test_timeout_from_connection_is_passed_to_transport(self):
		seen = {}

		def transport(method, url, headers, body, timeout):
			seen["timeout"] = timeout
			return Response(200, {}, b"{}")

		ODataClient(Connection(base_url="https://s4", timeout=7.5), transport=transport).get("S", "E")
		self.assertEqual(seen["timeout"], 7.5)


class TestGet(unittest.TestCase):
	def test_adds_json_format(self):
		fake = FakeS4HANA().on("GET", "E", ok({"a": 1}))
		self.assertEqual(client(fake).get("S", "E"), {"a": 1})
		self.assertEqual(fake.requests[0]["query"]["$format"], "json")
		self.assertEqual(fake.requests[0]["headers"]["Accept"], "application/json")

	def test_explicit_format_wins(self):
		fake = FakeS4HANA().on("GET", "E", ok({}))
		client(fake).get("S", "E", {"$format": "xml"})
		self.assertEqual(fake.requests[0]["query"]["$format"], "xml")

	def test_payload_without_d_wrapper(self):
		fake = FakeS4HANA().on("GET", "E", Response(200, {}, b'{"value": [1]}'))
		self.assertEqual(client(fake).get("S", "E"), {"value": [1]})

	def test_empty_body(self):
		fake = FakeS4HANA().on("GET", "E", Response(200, {}, b""))
		self.assertEqual(client(fake).get("S", "E"), {})

	def test_errors_raise(self):
		for status in (400, 401, 403, 500):
			fake = FakeS4HANA().on("GET", "E", sap_error(status, "C", "m"))
			with self.assertRaises(ODataError) as raised:
				client(fake).get("S", "E")
			self.assertEqual(raised.exception.status, status)
			# A failed read never changed anything in S/4HANA.
			self.assertFalse(raised.exception.maybe_applied)
		self.assertTrue(raised.exception.transient)

	def test_query_builds_filter_top_select(self):
		fake = FakeS4HANA().on("GET", "E", ok({"results": [{"a": 1}, {"a": 2}]}))
		rows = client(fake).query("S", "E", {"OrderID": "1", "Flag": True}, top=5, select=["a", "b"])
		self.assertEqual(rows, [{"a": 1}, {"a": 2}])
		query = fake.requests[0]["query"]
		self.assertEqual(query["$filter"], "OrderID eq '1' and Flag eq true")
		self.assertEqual((query["$top"], query["$select"]), ("5", "a,b"))

	def test_query_without_results(self):
		self.assertEqual(client(FakeS4HANA().on("GET", "E", ok({}))).query("S", "E", {"a": 1}), [])
		self.assertEqual(client(FakeS4HANA()).query("S", "E", {"a": 1}), [])  # 404 is an empty set


class TestCSRF(unittest.TestCase):
	def test_token_is_cached_per_service(self):
		fake = FakeS4HANA().on("FETCH", "S1", csrf("A")).on("FETCH", "S2", csrf("B"))
		c = client(fake)
		self.assertEqual((c.csrf_token("S1"), c.csrf_token("S2"), c.csrf_token("S1")), ("A", "B", "A"))
		self.assertEqual(len(fake.requests), 2)
		self.assertEqual(fake.requests[0]["headers"]["X-CSRF-Token"], "Fetch")

	def test_refresh_fetches_again(self):
		fake = FakeS4HANA().on("FETCH", "S", csrf("A"), once=True).on("FETCH", "S", csrf("B"))
		c = client(fake)
		self.assertEqual(c.csrf_token("S"), "A")
		self.assertEqual(c.csrf_token("S", refresh=True), "B")

	def test_fetch_without_token_or_with_error_raises(self):
		fake = FakeS4HANA().on("FETCH", "S", Response(200, {}, b""))
		with self.assertRaises(ODataError) as raised:
			client(fake).csrf_token("S")
		self.assertIn("CSRF", str(raised.exception))
		fake = FakeS4HANA().on("FETCH", "S", Response(401, {"x-csrf-token": "x"}, b""))
		with self.assertRaises(ODataError) as raised:
			client(fake).csrf_token("S")
		self.assertEqual(raised.exception.status, 401)
		fake = FakeS4HANA().on("FETCH", "S", Response(503, {}, b""))
		with self.assertRaises(ODataError) as raised:
			client(fake).csrf_token("S")
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)

	def test_post_gives_up_after_one_token_refresh(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "S", csrf("T"))
			.on("POST", "E", Response(403, {"x-csrf-token": "Required"}, b""))
		)
		with self.assertRaises(ODataError) as raised:
			client(fake).post("S", "E", {})
		self.assertEqual(raised.exception.status, 403)
		self.assertEqual([r["method"] for r in fake.requests], ["GET", "POST", "GET", "POST"])

	def test_plain_403_is_not_retried_with_a_new_token(self):
		# Without the "Required" header a 403 is a real denial: no second token fetch. The error is
		# transient (a fixed authorisation clears it) but nothing was applied.
		fake = (
			FakeS4HANA()
			.on("FETCH", "S", csrf("T"))
			.on("POST", "E", sap_error(403, "AUTH", "no authorisation"))
		)
		with self.assertRaises(ODataError) as raised:
			client(fake).post("S", "E", {})
		self.assertEqual([r["method"] for r in fake.requests], ["GET", "POST"])
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)

	def test_post_body_and_response(self):
		fake = FakeS4HANA().on("FETCH", "S", csrf("T")).on("POST", "E", ok({"Id": "9"}, 201))
		self.assertEqual(client(fake).post("S", "E", {"a": [1, 2]}), {"Id": "9"})
		post = fake.requests[1]
		self.assertEqual(post["body"], {"a": [1, 2]})
		self.assertEqual(post["headers"]["Content-Type"], "application/json")
		self.assertEqual(post["headers"]["X-CSRF-Token"], "T")
		self.assertEqual(post["query"], {"sap-client": "100"})

	def test_post_response_without_d_wrapper(self):
		fake = FakeS4HANA().on("FETCH", "S", csrf("T")).on("POST", "E", Response(201, {}, b'{"Id": "9"}'))
		self.assertEqual(client(fake).post("S", "E", {}), {"Id": "9"})


class TestErrorFromResponse(unittest.TestCase):
	def test_sap_error_body_with_details(self):
		body = {
			"error": {
				"code": "M7/053",
				"message": {"lang": "en", "value": "Period closed"},
				"innererror": {
					"errordetails": [{"code": "M7/053", "message": "Period 010 closed"}, {"code": "X"}]
				},
			}
		}
		error = error_from_response(Response(400, {}, json.dumps(body).encode()))
		self.assertEqual(str(error), "S/4HANA rejected the request (HTTP 400, M7/053): Period closed")
		self.assertEqual(
			error.details,
			[{"code": "M7/053", "message": "Period 010 closed"}, {"code": "X", "message": None}],
		)
		self.assertFalse(error.transient)
		self.assertFalse(error.maybe_applied)

	def test_non_json_body_is_quoted(self):
		error = error_from_response(Response(502, {}, b"<html>Bad Gateway</html>"))
		self.assertIn("Bad Gateway", str(error))
		self.assertTrue(error.transient)
		self.assertTrue(error.maybe_applied)

	def test_json_body_of_the_wrong_shape(self):
		# A body that is JSON but not SAP's error shape is quoted as text instead.
		error = error_from_response(Response(500, {}, b"[1, 2]"))
		self.assertEqual(str(error), "S/4HANA rejected the request (HTTP 500): [1, 2]")
		error = error_from_response(Response(500, {}, b'{"error": "text"}'))
		self.assertEqual(error.status, 500)

	def test_empty_body(self):
		error = error_from_response(Response(429, {}, b""), prefix="Throttled")
		self.assertEqual(str(error), "Throttled (HTTP 429)")
		self.assertTrue(error.transient)
		self.assertFalse(error.maybe_applied)

	def test_transient_statuses(self):
		self.assertEqual(TRANSIENT_STATUSES, {408, 429, 500, 502, 503, 504})
		for status in (400, 404, 409, 422):
			self.assertFalse(error_from_response(Response(status, {}, b"")).transient)
		for status in TRANSIENT_STATUSES | AUTH_STATUSES:
			self.assertTrue(error_from_response(Response(status, {}, b"")).transient)
		for status in AUTH_STATUSES:
			self.assertFalse(error_from_response(Response(status, {}, b"")).maybe_applied)

	def test_long_body_is_truncated(self):
		error = error_from_response(Response(500, {}, b"x" * 2000))
		self.assertLess(len(str(error)), 600)


class TestLiterals(unittest.TestCase):
	def test_literal_kinds(self):
		self.assertEqual(literal(True), "true")
		self.assertEqual(literal(False), "false")
		self.assertEqual(literal(5), "5")
		self.assertEqual(literal(2.5), "2.5")
		self.assertEqual(literal("a'b"), "'a''b'")
		self.assertEqual(literal(""), "''")
		self.assertEqual(literal(None), "'None'")

	def test_key_predicate_encodes_each_value(self):
		self.assertEqual(key_predicate({"A": "x y", "B": "ä"}), "(A='x%20y',B='%C3%A4')")
		self.assertEqual(key_predicate({"N": 5}), "(5)")
		self.assertEqual(key_predicate({"A": "a/b"}), "('a%2Fb')")

	def test_filter_expression_with_one_and_many(self):
		self.assertEqual(filter_expression({"A": "x"}), "A eq 'x'")
		self.assertEqual(filter_expression({}), "")
		self.assertEqual(filter_expression({"A": 1, "B": False}), "A eq 1 and B eq false")


class TestFake(unittest.TestCase):
	def test_default_is_404_and_once_rules_expire(self):
		fake = FakeS4HANA().on("GET", "E", ok({"n": 1}), once=True)
		self.assertEqual(client(fake).get("S", "E"), {"n": 1})
		self.assertIsNone(client(fake).get("S", "E"))

	def test_callable_rule_sees_the_request(self):
		fake = FakeS4HANA().on("GET", "E", lambda request: ok({"path": request["path"]}))
		self.assertEqual(client(fake).get("S", "E")["path"], "/sap/opu/odata/sap/S/E")


if __name__ == "__main__":
	unittest.main()
