# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The REST client against the scripted fake: URLs, both token flows, collection envelopes and the
platform's error body. No Frappe site needed."""

import base64
import unittest

from foames.foames_adapters.insights_hub import rest
from foames.foames_adapters.insights_hub.fake import FakeInsightsHub, hub_error, ok, page, token
from foames.foames_adapters.insights_hub.rest import (
	SERVICE_CREDENTIALS,
	Connection,
	InsightsHubError,
	Response,
	RestClient,
	items_of,
	json_filter,
)

GATEWAY = "https://gateway.eu1.example"


def client(fake=None, **overrides):
	connection = Connection(
		gateway_url=GATEWAY,
		tenant="plant1",
		client_id="app-client",
		client_secret="s3cret",
		app_name="foames",
		app_version="1.0.0",
	)
	for name, value in overrides.items():
		setattr(connection, name, value)
	return RestClient(connection, transport=fake or FakeInsightsHub())


class TestUrls(unittest.TestCase):
	def test_paths_sit_behind_the_gateway(self):
		c = client(Connection(gateway_url=GATEWAY + "/"))
		self.assertEqual(c.url("assetmanagement/v3/assets"), GATEWAY + "/api/assetmanagement/v3/assets")
		self.assertEqual(c.url("/assetmanagement/v3/assets/x"), GATEWAY + "/api/assetmanagement/v3/assets/x")

	def test_query_values_are_encoded(self):
		url = client().url(
			"eventmanagement/v3/events", {"filter": json_filter({"a": "b c"}), "size": "2", "x": None}
		)
		self.assertEqual(
			url, GATEWAY + "/api/eventmanagement/v3/events?filter=%7B%22a%22%3A%22b%20c%22%7D&size=2"
		)


class TestTokens(unittest.TestCase):
	def test_token_manager_request(self):
		fake = FakeInsightsHub()
		c = client(fake)
		self.assertEqual(c.access_token(), "T1")
		request = fake.requests[0]
		self.assertEqual(request["method"], "POST")
		self.assertEqual(request["path"], "/api/technicaltokenmanager/v3/oauth/token")
		expected = base64.b64encode(b"app-client:s3cret").decode()
		self.assertEqual(request["headers"]["X-SPACE-AUTH-KEY"], "Bearer " + expected)
		self.assertEqual(
			request["body"],
			{"appName": "foames", "appVersion": "1.0.0", "hostTenant": "plant1", "userTenant": "plant1"},
		)

	def test_token_manager_tenants_can_differ(self):
		fake = FakeInsightsHub()
		client(fake, host_tenant="vendor", user_tenant="plant1").access_token()
		self.assertEqual(
			(fake.requests[0]["body"]["hostTenant"], fake.requests[0]["body"]["userTenant"]),
			("vendor", "plant1"),
		)

	def test_service_credentials_request(self):
		fake = FakeInsightsHub()
		c = client(fake, auth=SERVICE_CREDENTIALS, token_url="https://plant1.piam.eu1.example/oauth/token")
		c.access_token()
		request = fake.requests[0]
		self.assertEqual(request["url"], "https://plant1.piam.eu1.example/oauth/token")
		expected = base64.b64encode(b"app-client:s3cret").decode()
		self.assertEqual(request["headers"]["Authorization"], "Basic " + expected)
		self.assertEqual(request["body"], b"grant_type=client_credentials")

	def test_service_credentials_need_a_token_url(self):
		with self.assertRaises(InsightsHubError):
			client(auth=SERVICE_CREDENTIALS, token_url="").access_token()

	def test_token_is_cached_until_it_nears_expiry(self):
		fake = FakeInsightsHub().on("POST", "oauth/token", token("T2", expires_in=1799))
		c = client(fake)
		c.get("assetmanagement/v3/assets/a")
		c.get("assetmanagement/v3/assets/a")
		self.assertEqual(len([r for r in fake.requests if "oauth/token" in r["path"]]), 1)
		self.assertEqual(fake.requests[1]["headers"]["Authorization"], "Bearer T2")

	def test_expiring_token_is_fetched_again(self):
		fake = FakeInsightsHub().on("POST", "oauth/token", token("T3", expires_in=10))
		c = client(fake)
		c.access_token()
		c.access_token()
		self.assertEqual(len(fake.requests), 2)

	def test_rejected_login_is_transient(self):
		fake = FakeInsightsHub().on(
			"POST", "oauth/token", hub_error(401, "mdsp.core.generic.unauthorized", "bad")
		)
		with self.assertRaises(InsightsHubError) as raised:
			client(fake).access_token()
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)
		self.assertIn("token request failed", str(raised.exception))

	def test_token_without_access_token_is_an_error(self):
		fake = FakeInsightsHub().on("POST", "oauth/token", ok({"token_type": "bearer"}))
		with self.assertRaises(InsightsHubError):
			client(fake).access_token()


class TestReads(unittest.TestCase):
	def test_get_returns_json_and_none_for_404(self):
		fake = FakeInsightsHub().on("GET", "/assets/a1", ok({"assetId": "a1", "name": "Press"}))
		c = client(fake)
		self.assertEqual(c.get("assetmanagement/v3/assets/a1")["name"], "Press")
		self.assertIsNone(c.get("assetmanagement/v3/assets/missing"))
		self.assertEqual(fake.requests[1]["headers"]["Accept"], "application/json")

	def test_get_page_unwraps_the_embedded_list(self):
		fake = FakeInsightsHub().on("GET", "/assets", page([{"assetId": "a1"}], total=7))
		rows = client(fake).get_page(
			"assetmanagement/v3/assets", {"filter": json_filter({"name": "P"})}, size=2
		)
		self.assertEqual(rows, [{"assetId": "a1"}])
		query = fake.requests[-1]["query"]
		self.assertEqual((query["page"], query["size"], query["filter"]), ("0", "2", {"name": "P"}))

	def test_items_of_every_envelope(self):
		self.assertEqual(items_of(None), [])
		self.assertEqual(items_of([1]), [1])
		self.assertEqual(items_of({"_embedded": {"events": [1, 2]}}), [1, 2])
		self.assertEqual(items_of({"_embedded": {}}), [])
		self.assertEqual(items_of({"content": [3]}), [3])
		self.assertEqual(items_of({"other": 1}), [])
		self.assertEqual(items_of("text"), [])

	def test_read_errors_never_count_as_applied(self):
		fake = FakeInsightsHub().on("GET", "/assets", hub_error(500, "mdsp.core.generic.internal", "boom"))
		with self.assertRaises(InsightsHubError) as raised:
			client(fake).get("assetmanagement/v3/assets/a")
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)


class TestWrites(unittest.TestCase):
	def test_put_sends_json_and_accepts_no_content(self):
		fake = FakeInsightsHub().on("PUT", "/timeseries/", Response(204, {}, b""))
		result = client(fake).write(
			"PUT", "iottimeseries/v3/timeseries/a1/Prod", [{"_time": "t", "x": 1}], idempotent=True
		)
		self.assertIsNone(result)
		request = fake.requests[-1]
		self.assertEqual(request["headers"]["Content-Type"], "application/json")
		self.assertEqual(request["body"], [{"_time": "t", "x": 1}])

	def test_post_returns_the_created_record(self):
		fake = FakeInsightsHub().on("POST", "/events", ok({"id": "e1"}, 201))
		self.assertEqual(client(fake).write("POST", "eventmanagement/v3/events", {"a": 1})["id"], "e1")

	def test_validation_error_is_final(self):
		fake = FakeInsightsHub().on(
			"POST", "/events", hub_error(400, "mdsp.core.eventmanagement.invalid", "bad field")
		)
		with self.assertRaises(InsightsHubError) as raised:
			client(fake).write("POST", "eventmanagement/v3/events", {})
		e = raised.exception
		self.assertEqual(
			(e.status, e.code, e.transient, e.maybe_applied),
			(400, "mdsp.core.eventmanagement.invalid", False, False),
		)
		self.assertIn("bad field", str(e))
		self.assertEqual(e.details[0]["logref"], "a1b2c3")

	def test_server_error_on_a_write_may_have_applied(self):
		fake = FakeInsightsHub().on("POST", "/events", hub_error(503, "x", "down"))
		with self.assertRaises(InsightsHubError) as raised:
			client(fake).write("POST", "eventmanagement/v3/events", {})
		self.assertTrue(raised.exception.transient)
		self.assertTrue(raised.exception.maybe_applied)

	def test_server_error_on_an_idempotent_write_needs_no_check(self):
		fake = FakeInsightsHub().on("PUT", "/timeseries/", hub_error(502, "x", "gateway"))
		with self.assertRaises(InsightsHubError) as raised:
			client(fake).write("PUT", "iottimeseries/v3/timeseries/a/b", [], idempotent=True)
		self.assertTrue(raised.exception.transient)
		self.assertFalse(raised.exception.maybe_applied)

	def test_network_failures(self):
		for error in (TimeoutError(), ConnectionResetError(), OSError("dns")):
			fake = FakeInsightsHub().on("POST", "/events", error)
			with self.assertRaises(InsightsHubError) as raised:
				client(fake).write("POST", "eventmanagement/v3/events", {})
			self.assertTrue(raised.exception.transient)
			self.assertTrue(raised.exception.maybe_applied)
			read = FakeInsightsHub().on("GET", "/assets", error)
			with self.assertRaises(InsightsHubError) as raised:
				client(read).get("assetmanagement/v3/assets/a")
			self.assertFalse(raised.exception.maybe_applied)

	def test_throttling_is_transient(self):
		fake = FakeInsightsHub().on(
			"GET", "/assets", hub_error(429, "mdsp.core.generic.tooManyRequests", "slow down")
		)
		with self.assertRaises(InsightsHubError) as raised:
			client(fake).get("assetmanagement/v3/assets/a")
		self.assertTrue(raised.exception.transient)

	def test_error_body_variants(self):
		plain = rest.error_from_response(Response(400, {}, b"not json"))
		self.assertIn("not json", str(plain))
		message = rest.error_from_response(Response(400, {}, b'{"message": "m"}'))
		self.assertIn(": m", str(message))
		empty = rest.error_from_response(Response(500, {}, b""))
		self.assertEqual(str(empty), "Insights Hub rejected the request (HTTP 500)")


if __name__ == "__main__":
	unittest.main()
