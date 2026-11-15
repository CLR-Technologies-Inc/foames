import unittest

from foames.foames_adapters.s4hana import odata, outbox
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.foames_adapters.s4hana.odata import Connection, ODataClient, Response


def client(fake):
	return ODataClient(Connection(base_url="https://s4", client="100"), transport=fake)


class FakeOutboxRow:
	"""What the S4HANA Outbox DocType does with an Outcome: verify first after an Unknown."""

	def __init__(self):
		self.status = "Queued"

	@property
	def verify_first(self):
		return self.status == "Unknown"


class TestNoDuplicatePostings(unittest.TestCase):
	operation = outbox.OPERATIONS["Production Order Confirmation"]

	def payload(self):
		return outbox.prepare(
			self.operation, {"OrderID": "1000123", "ConfirmationYieldQuantity": "40"}, "conf-1"
		)

	def posts(self, fake):
		return [r for r in fake.requests if r["method"] == "POST"]

	def test_gateway_timeout_then_retry_posts_once(self):
		created = {"ConfirmationGroup": "77", "ConfirmationCount": "1"}
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf())
			.on("POST", "ProdnOrdConf2", sap_error(504, "GW", "Gateway timeout"), once=True)
			.on("GET", "ProdnOrdConf2", ok({"results": [created]}))
			.on("POST", "ProdnOrdConf2", ok(created, 201))
		)
		row = FakeOutboxRow()
		first = outbox.send(client(fake), self.operation, self.payload(), verify_first=row.verify_first)
		self.assertEqual(first.status, "Unknown")
		row.status = first.status
		second = outbox.send(client(fake), self.operation, self.payload(), verify_first=row.verify_first)
		self.assertEqual((second.status, second.document), ("Posted", "77|1"))
		self.assertEqual(len(self.posts(fake)), 1, "the confirmation was posted twice")

	def test_connection_reset_on_post_is_unknown(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf())
			.on("POST", "ProdnOrdConf2", ConnectionResetError())
		)
		self.assertEqual(
			outbox.send(client(fake), self.operation, self.payload(), verify_first=False).status, "Unknown"
		)

	def test_every_5xx_on_a_write_is_unknown(self):
		for status in (500, 502, 503, 504):
			fake = (
				FakeS4HANA()
				.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf())
				.on("POST", "ProdnOrdConf2", Response(status, {"Retry-After": "60"}, b""))
			)
			outcome = outbox.send(client(fake), self.operation, self.payload(), verify_first=False)
			self.assertEqual(outcome.status, "Unknown", status)

	def test_throttling_before_the_write_is_a_plain_retry(self):
		fake = FakeS4HANA().on(
			"FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", Response(429, {"Retry-After": "5"}, b"")
		)
		self.assertEqual(
			outbox.send(client(fake), self.operation, self.payload(), verify_first=False).status, "Retry"
		)
		self.assertEqual(self.posts(fake), [])

	def test_business_rejection_still_fails(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf())
			.on("POST", "ProdnOrdConf2", sap_error(400, "RU/505", "Order is locked"))
		)
		self.assertEqual(
			outbox.send(client(fake), self.operation, self.payload(), verify_first=False).status, "Failed"
		)

	def test_marker_is_stable(self):
		self.assertEqual(outbox.marker("conf-1"), outbox.marker("conf-1"))
		self.assertEqual(len(outbox.marker("conf-1")), 23)

	def test_give_up_unchanged(self):
		self.assertFalse(outbox.give_up(outbox.MAX_ATTEMPTS - 1))
		self.assertTrue(outbox.give_up(outbox.MAX_ATTEMPTS))

	def test_retry_after_never_shortens_the_wait(self):
		for attempts in range(1, 13):
			for asked in (0, 1, 30, 600):
				self.assertGreaterEqual(
					outbox.retry_delay(attempts, retry_after=asked), outbox.retry_delay(attempts)
				)

	def test_modules_stay_pure(self):
		for module in (outbox, odata):
			source = open(module.__file__, encoding="utf-8").read()
			self.assertNotIn("import frappe", source)
			self.assertNotIn("from frappe", source)
