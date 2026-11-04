# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json

import frappe

from foames.foames_adapters.doctype.insights_hub_outbox.insights_hub_outbox import enqueue, process_outbox
from foames.foames_adapters.insights_hub import outbox
from foames.foames_adapters.insights_hub.fake import FakeInsightsHub, hub_error, no_content, ok, page
from foames.tests_compat import IntegrationTestCase

RECORD = {"_time": "2026-11-04T10:00:00.000Z", "goodCount": 12, "scrapCount": 1, "runMinutes": 9.5}
TIME_SERIES = {"entityId": "a1", "propertySetName": "FoaMESProduction", "data": [RECORD]}
EVENT = {
	"entityId": "a1",
	"timestamp": "2026-11-04T10:00:00.000Z",
	"severity": 20,
	"description": "Press 1 is Down",
}


def enable_insights_hub():
	settings = frappe.get_single("Insights Hub Settings")
	settings.update(
		{
			"enabled": 1,
			"gateway_url": "https://gateway.eu1.example",
			"tenant": "plant1",
			"auth_method": "Technical Token Manager",
			"client_id": "app-client",
			"client_secret": "secret",
			"app_name": "foames",
			"app_version": "1.0.0",
			"outbox_paused": 0,
		}
	)
	settings.save()


class TestInsightsHubOutbox(IntegrationTestCase):
	def setUp(self):
		enable_insights_hub()
		frappe.db.delete("Insights Hub Outbox")
		self.addCleanup(self.clean_up)

	def clean_up(self):
		# The outbox commits after each posting, so a rollback alone does not undo a test.
		frappe.db.rollback()
		frappe.db.delete("Insights Hub Outbox")
		settings = frappe.get_single("Insights Hub Settings")
		settings.enabled = 0
		settings.outbox_paused = 0
		settings.save()
		frappe.db.commit()  # nosemgrep

	def test_enqueue_is_idempotent(self):
		first = enqueue("Time Series Write", TIME_SERIES, "press-1:timeseries:1")
		self.assertEqual(enqueue("Time Series Write", TIME_SERIES, "press-1:timeseries:1"), first)
		self.assertEqual(frappe.db.count("Insights Hub Outbox"), 1)

	def test_enqueue_validates_payload(self):
		with self.assertRaises(frappe.ValidationError):
			enqueue("Time Series Write", {"entityId": "a1", "propertySetName": "P", "data": []}, "empty")
		with self.assertRaises(frappe.ValidationError):
			enqueue("Goods Movement", TIME_SERIES, "wrong-operation")

	def test_time_series_is_put_on_the_asset(self):
		name = enqueue("Time Series Write", TIME_SERIES, "press-1:timeseries:1")
		fake = FakeInsightsHub().on("PUT", "/timeseries/a1/FoaMESProduction", no_content())
		process_outbox(transport=fake)
		doc = frappe.get_doc("Insights Hub Outbox", name)
		self.assertEqual(
			(doc.status, doc.hub_document, doc.attempts),
			("Posted", "a1/FoaMESProduction@2026-11-04T10:00:00.000Z", 1),
		)
		put = next(r for r in fake.requests if r["method"] == "PUT")
		self.assertEqual(put["body"], [RECORD])
		token = next(r for r in fake.requests if "oauth/token" in r["path"])
		self.assertEqual(token["body"]["appName"], "foames")

	def test_event_carries_the_marker(self):
		name = enqueue("Event", EVENT, "press-1:state:Down:1")
		fake = FakeInsightsHub().on("POST", "/events", ok({"id": "e1"}, 201))
		process_outbox(transport=fake)
		doc = frappe.get_doc("Insights Hub Outbox", name)
		self.assertEqual((doc.status, doc.hub_document), ("Posted", "e1"))
		post = next(r for r in fake.requests if r["method"] == "POST" and "events" in r["path"])
		self.assertEqual(post["body"]["correlationId"], outbox.marker("press-1:state:Down:1"))
		self.assertEqual(json.loads(doc.sent_payload)["typeId"], outbox.STANDARD_EVENT_TYPE)

	def test_rejection_fails_and_holds_its_group(self):
		first = enqueue("Event", EVENT, "a", sequence_group="asset:a1")
		second = enqueue("Event", EVENT, "b", sequence_group="asset:a1")
		fake = FakeInsightsHub().on(
			"POST", "/events", hub_error(400, "mdsp.core.eventmanagement.invalid", "bad")
		)
		process_outbox(transport=fake)
		self.assertEqual(frappe.db.get_value("Insights Hub Outbox", first, "status"), "Failed")
		self.assertEqual(frappe.db.get_value("Insights Hub Outbox", second, "status"), "Queued")
		self.assertEqual(
			len([r for r in fake.requests if r["method"] == "POST" and "events" in r["path"]]), 1
		)

		# Cancelling the failed posting releases the next one.
		frappe.get_doc("Insights Hub Outbox", first).cancel_posting()
		process_outbox(transport=FakeInsightsHub().on("POST", "/events", ok({"id": "e2"}, 201)))
		self.assertEqual(frappe.db.get_value("Insights Hub Outbox", second, "status"), "Posted")

	def test_event_timeout_is_verified_before_resending(self):
		name = enqueue("Event", EVENT, "press-1:state:Down:2")
		fake = FakeInsightsHub().on("POST", "/events", TimeoutError("t"))
		process_outbox(transport=fake)
		doc = frappe.get_doc("Insights Hub Outbox", name)
		self.assertEqual(doc.status, "Unknown")
		self.assertTrue(doc.next_attempt_at)

		frappe.db.set_value("Insights Hub Outbox", name, "next_attempt_at", None)
		existing = {"id": "e7", "correlationId": outbox.marker("press-1:state:Down:2")}
		fake = FakeInsightsHub().on("GET", "/events", page([existing], "events"))
		process_outbox(transport=fake)
		doc.reload()
		self.assertEqual((doc.status, doc.hub_document), ("Posted", "e7"))
		self.assertFalse([r for r in fake.requests if r["method"] == "POST" and "events" in r["path"]])

	def test_time_series_timeout_is_simply_retried(self):
		name = enqueue("Time Series Write", TIME_SERIES, "press-1:timeseries:2")
		process_outbox(transport=FakeInsightsHub().on("PUT", "/timeseries/", TimeoutError("t")))
		doc = frappe.get_doc("Insights Hub Outbox", name)
		self.assertEqual(doc.status, "Retry")

		frappe.db.set_value("Insights Hub Outbox", name, "next_attempt_at", None)
		fake = FakeInsightsHub().on("PUT", "/timeseries/", no_content())
		process_outbox(transport=fake)
		doc.reload()
		self.assertEqual((doc.status, doc.attempts), ("Posted", 2))
		self.assertEqual([r["method"] for r in fake.requests if "oauth" not in r["path"]], ["PUT"])

	def test_paused_outbox_sends_nothing(self):
		settings = frappe.get_single("Insights Hub Settings")
		settings.outbox_paused = 1
		settings.save()
		enqueue("Time Series Write", TIME_SERIES, "paused")
		fake = FakeInsightsHub().on("PUT", "/timeseries/", no_content())
		process_outbox(transport=fake)
		self.assertEqual(fake.requests, [])

	def test_requeue_checks_first(self):
		name = enqueue("Event", EVENT, "requeue")
		process_outbox(transport=FakeInsightsHub().on("POST", "/events", hub_error(400, "x", "bad")))
		doc = frappe.get_doc("Insights Hub Outbox", name)
		self.assertEqual(doc.status, "Failed")
		doc.requeue()
		self.assertEqual((doc.status, doc.attempts), ("Unknown", 0))
