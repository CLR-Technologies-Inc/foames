# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The outbox rules on their own: markers, prepared payloads, the verify-first search and the
outcome of every kind of answer. No Frappe site needed."""

import unittest
from datetime import datetime, timedelta, timezone

from foames.foames_adapters.insights_hub import outbox
from foames.foames_adapters.insights_hub.fake import FakeInsightsHub, hub_error, no_content, ok, page
from foames.foames_adapters.insights_hub.rest import Connection, RestClient

RECORD = {"_time": "2026-11-04T10:00:00.000Z", "goodCount": 12, "scrapCount": 1}
TIME_SERIES = {"entityId": "a1", "propertySetName": "FoaMESProduction", "data": [RECORD]}
EVENT = {
	"entityId": "a1",
	"timestamp": "2026-11-04T10:00:00.000Z",
	"severity": 20,
	"description": "Press 1 is Down",
}


def client(fake):
	return RestClient(
		Connection(gateway_url="https://gw", client_id="c", client_secret="s", app_name="a"), transport=fake
	)


class TestOperations(unittest.TestCase):
	def test_catalogue(self):
		self.assertEqual(outbox.operation_names(), ["Time Series Write", "Event"])
		self.assertTrue(outbox.operation("Time Series Write").idempotent)
		self.assertFalse(outbox.operation("Event").idempotent)
		with self.assertRaises(KeyError):
			outbox.operation("Goods Movement")

	def test_marker_shape(self):
		mark = outbox.marker("any key")
		self.assertTrue(mark.startswith(outbox.MARKER_PREFIX))
		self.assertEqual(len(mark), 23)
		int(mark[len(outbox.MARKER_PREFIX) :], 16)
		self.assertNotEqual(mark, outbox.marker("other key"))


class TestPrepare(unittest.TestCase):
	def test_time_series_is_copied_and_checked(self):
		prepared = outbox.prepare(outbox.operation(outbox.TIME_SERIES), TIME_SERIES, "k")
		self.assertEqual(prepared, TIME_SERIES)
		self.assertIsNot(prepared, TIME_SERIES)
		for bad in (
			{"entityId": "a1", "data": [RECORD]},
			{"entityId": "a1", "propertySetName": "P", "data": []},
			{"entityId": "a1", "propertySetName": "P", "data": [{"goodCount": 1}]},
			{"entityId": "a1", "propertySetName": "P", "data": {"_time": "t"}},
		):
			with self.assertRaises(ValueError, msg=bad):
				outbox.prepare(outbox.operation(outbox.TIME_SERIES), bad, "k")

	def test_event_gets_the_marker_and_the_standard_type(self):
		prepared = outbox.prepare(outbox.operation(outbox.EVENT), EVENT, "k")
		self.assertEqual(prepared["correlationId"], outbox.marker("k"))
		self.assertEqual(prepared["typeId"], outbox.STANDARD_EVENT_TYPE)
		self.assertNotIn("correlationId", EVENT)
		custom = outbox.prepare(
			outbox.operation(outbox.EVENT), {**EVENT, "typeId": "my.type", "correlationId": "mine"}, "k"
		)
		self.assertEqual((custom["typeId"], custom["correlationId"]), ("my.type", outbox.marker("k")))
		with self.assertRaises(ValueError) as raised:
			outbox.prepare(outbox.operation(outbox.EVENT), {"entityId": "a1"}, "k")
		self.assertIn("timestamp", str(raised.exception))


class TestDocumentIds(unittest.TestCase):
	def test_time_series_names_the_asset_aspect_and_last_time(self):
		payload = {**TIME_SERIES, "data": [RECORD, {**RECORD, "_time": "2026-11-04T10:10:00.000Z"}]}
		self.assertEqual(
			outbox.document_id(outbox.operation(outbox.TIME_SERIES), payload, None),
			"a1/FoaMESProduction@2026-11-04T10:10:00.000Z",
		)

	def test_event_uses_its_id(self):
		self.assertEqual(outbox.document_id(outbox.operation(outbox.EVENT), EVENT, {"id": "e9"}), "e9")
		self.assertEqual(outbox.document_id(outbox.operation(outbox.EVENT), EVENT, None), "")


class TestSend(unittest.TestCase):
	def test_time_series_is_put_on_the_asset(self):
		fake = FakeInsightsHub().on("PUT", "/timeseries/a1/FoaMESProduction", no_content())
		outcome = outbox.send(
			client(fake), outbox.operation(outbox.TIME_SERIES), TIME_SERIES, verify_first=False
		)
		self.assertEqual(
			(outcome.status, outcome.document), ("Posted", "a1/FoaMESProduction@2026-11-04T10:00:00.000Z")
		)
		put = next(r for r in fake.requests if r["method"] == "PUT")
		self.assertEqual(put["path"], "/api/iottimeseries/v3/timeseries/a1/FoaMESProduction")
		self.assertEqual(put["body"], [RECORD])

	def test_time_series_verify_first_just_sends_again(self):
		fake = FakeInsightsHub().on("PUT", "/timeseries/", no_content())
		outcome = outbox.send(
			client(fake), outbox.operation(outbox.TIME_SERIES), TIME_SERIES, verify_first=True
		)
		self.assertEqual(outcome.status, "Posted")
		self.assertEqual([r["method"] for r in fake.requests if "oauth" not in r["path"]], ["PUT"])

	def test_time_series_failures(self):
		rejected = FakeInsightsHub().on(
			"PUT", "/timeseries/", hub_error(400, "mdsp.core.iottimeseries.badRequest", "no such variable")
		)
		outcome = outbox.send(client(rejected), outbox.operation(outbox.TIME_SERIES), TIME_SERIES, False)
		self.assertEqual(outcome.status, "Failed")
		self.assertIn("no such variable", outcome.error)
		self.assertEqual(outcome.details[0]["code"], "mdsp.core.iottimeseries.badRequest")
		for answer in (hub_error(503, "x", "down"), TimeoutError("t"), hub_error(401, "x", "expired")):
			fake = FakeInsightsHub().on("PUT", "/timeseries/", answer)
			outcome = outbox.send(client(fake), outbox.operation(outbox.TIME_SERIES), TIME_SERIES, True)
			# An upsert can be sent again without checking, so it is never Unknown.
			self.assertEqual(outcome.status, "Retry", msg=answer)

	def test_event_is_posted(self):
		fake = FakeInsightsHub().on("POST", "/events", ok({"id": "e1", "correlationId": "x"}, 201))
		prepared = outbox.prepare(outbox.operation(outbox.EVENT), EVENT, "k")
		outcome = outbox.send(client(fake), outbox.operation(outbox.EVENT), prepared, verify_first=False)
		self.assertEqual((outcome.status, outcome.document, outcome.response["id"]), ("Posted", "e1", "e1"))
		post = next(r for r in fake.requests if r["method"] == "POST" and "events" in r["path"])
		self.assertEqual(post["path"], "/api/eventmanagement/v3/events")
		self.assertEqual(post["body"]["correlationId"], outbox.marker("k"))

	def test_event_outcomes(self):
		prepared = outbox.prepare(outbox.operation(outbox.EVENT), EVENT, "k")
		for answer, verify, expected in (
			(hub_error(400, "x", "bad"), False, "Failed"),
			(hub_error(503, "x", "down"), False, "Unknown"),
			(hub_error(429, "x", "slow"), False, "Retry"),
			(hub_error(429, "x", "slow"), True, "Unknown"),
			(TimeoutError("t"), False, "Unknown"),
		):
			fake = FakeInsightsHub().on("GET", "/events", page([], "events")).on("POST", "/events", answer)
			outcome = outbox.send(client(fake), outbox.operation(outbox.EVENT), prepared, verify_first=verify)
			self.assertEqual(outcome.status, expected, msg=(answer, verify))

	def test_event_verify_first_finds_the_earlier_one(self):
		prepared = outbox.prepare(outbox.operation(outbox.EVENT), EVENT, "k")
		existing = {"id": "e7", "correlationId": outbox.marker("k")}
		other = {"id": "e8", "correlationId": "something else"}
		fake = FakeInsightsHub().on("GET", "/events", page([other, existing], "events"))
		outcome = outbox.send(client(fake), outbox.operation(outbox.EVENT), prepared, verify_first=True)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "e7"))
		self.assertFalse([r for r in fake.requests if r["method"] == "POST" and "events" in r["path"]])
		search = next(r for r in fake.requests if r["method"] == "GET")
		self.assertEqual(search["query"]["filter"]["entityId"], "a1")
		self.assertEqual(search["query"]["filter"]["typeId"], outbox.STANDARD_EVENT_TYPE)
		self.assertEqual(
			search["query"]["filter"]["timestamp"],
			{"between": "[2026-11-04T09:59:00.000Z,2026-11-04T10:01:00.000Z]"},
		)

	def test_event_verify_first_posts_when_nothing_matches(self):
		prepared = outbox.prepare(outbox.operation(outbox.EVENT), EVENT, "k")
		fake = (
			FakeInsightsHub()
			.on("GET", "/events", page([], "events"))
			.on("POST", "/events", ok({"id": "e1"}, 201))
		)
		outcome = outbox.send(client(fake), outbox.operation(outbox.EVENT), prepared, verify_first=True)
		self.assertEqual((outcome.status, outcome.document), ("Posted", "e1"))

	def test_failed_search_is_retried_not_failed(self):
		prepared = outbox.prepare(outbox.operation(outbox.EVENT), EVENT, "k")
		fake = FakeInsightsHub().on("GET", "/events", hub_error(503, "x", "down"))
		outcome = outbox.send(client(fake), outbox.operation(outbox.EVENT), prepared, verify_first=True)
		self.assertEqual(outcome.status, "Unknown")


class TestRetryPolicy(unittest.TestCase):
	def test_backoff_doubles_and_caps(self):
		self.assertEqual([outbox.retry_delay(n) for n in (0, 1, 2, 3, 4)], [60, 60, 120, 240, 480])
		self.assertEqual(outbox.retry_delay(50), outbox.MAX_DELAY_SECONDS)

	def test_give_up(self):
		self.assertFalse(outbox.give_up(outbox.MAX_ATTEMPTS - 1))
		self.assertTrue(outbox.give_up(outbox.MAX_ATTEMPTS))


class TestTime(unittest.TestCase):
	def test_iso_utc(self):
		self.assertEqual(outbox.iso_utc(datetime(2026, 11, 4, 10, 0, 0, 123456)), "2026-11-04T10:00:00.123Z")
		cet = timezone(timedelta(hours=1))
		self.assertEqual(outbox.iso_utc(datetime(2026, 11, 4, 11, 0, tzinfo=cet)), "2026-11-04T10:00:00.000Z")

	def test_parse_time(self):
		parsed = outbox.parse_time("2026-11-04T10:00:00.500Z")
		self.assertEqual(parsed, datetime(2026, 11, 4, 10, 0, 0, 500000, tzinfo=timezone.utc))
		self.assertEqual(outbox.parse_time("2026-11-04T11:00:00+01:00"), parsed.replace(microsecond=0))
		self.assertEqual(outbox.parse_time(datetime(2026, 1, 1)).tzinfo, timezone.utc)
		self.assertIsNone(outbox.parse_time("yesterday"))
		self.assertIsNone(outbox.parse_time(None))


if __name__ == "__main__":
	unittest.main()
