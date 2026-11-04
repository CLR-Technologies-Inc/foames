import time
import unittest
from email.utils import formatdate

from foames.foames_adapters.s4hana import outbox
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf
from foames.foames_adapters.s4hana.odata import (
	Connection,
	ODataClient,
	ODataError,
	Response,
	error_from_response,
)


def client(fake):
	return ODataClient(Connection(base_url="https://s4", client="100"), transport=fake)


class TestRetryAfterParsing(unittest.TestCase):
	def test_seconds(self):
		self.assertEqual(error_from_response(Response(429, {"Retry-After": "300"}, b"")).retry_after, 300)

	def test_header_name_is_case_insensitive(self):
		self.assertEqual(error_from_response(Response(503, {"retry-after": "120"}, b"")).retry_after, 120)

	def test_http_date(self):
		when = formatdate(time.time() + 600, usegmt=True)
		seconds = error_from_response(Response(503, {"Retry-After": when}, b"")).retry_after
		self.assertIsInstance(seconds, int)
		self.assertTrue(570 <= seconds <= 630, seconds)

	def test_missing_or_unreadable(self):
		self.assertIsNone(error_from_response(Response(503, {}, b"")).retry_after)
		self.assertIsNone(error_from_response(Response(429, {"Retry-After": "soon"}, b"")).retry_after)

	def test_odata_error_default(self):
		self.assertIsNone(ODataError("x").retry_after)


class TestRetryDelay(unittest.TestCase):
	def test_server_asks_for_longer(self):
		self.assertEqual(outbox.retry_delay(1, retry_after=300), 300)
		self.assertEqual(outbox.retry_delay(2, retry_after=900), 900)

	def test_backoff_wins_when_longer(self):
		self.assertEqual(outbox.retry_delay(4, retry_after=30), 480)

	def test_capped(self):
		self.assertEqual(outbox.retry_delay(1, retry_after=10 * 24 * 3600), outbox.MAX_DELAY_SECONDS)

	def test_none_is_unchanged(self):
		for attempts in range(1, 15):
			self.assertEqual(
				outbox.retry_delay(attempts, retry_after=None),
				min(outbox.BASE_DELAY_SECONDS * 2 ** (attempts - 1), outbox.MAX_DELAY_SECONDS),
			)


class TestOutcomeCarriesRetryAfter(unittest.TestCase):
	operation = outbox.OPERATIONS["Goods Movement"]

	def payload(self):
		return outbox.prepare(self.operation, {"GoodsMovementCode": "02"}, "gr-1")

	def test_throttled_post(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "A_MaterialDocumentHeader", Response(429, {"Retry-After": "300"}, b""))
		)
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual(outcome.status, "Retry")
		self.assertEqual(outcome.retry_after, 300)

	def test_throttled_csrf_fetch(self):
		fake = FakeS4HANA().on(
			"FETCH", "API_MATERIAL_DOCUMENT_SRV", Response(503, {"Retry-After": "120"}, b"")
		)
		outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
		self.assertEqual(outcome.status, "Retry")
		self.assertEqual(outcome.retry_after, 120)

	def test_default(self):
		self.assertIsNone(outbox.Outcome("Retry").retry_after)
