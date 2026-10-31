# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The machine-event webhook end to end on a Frappe site: signatures, roles, body shapes, time zones
and what processing does for a Guest caller."""

import json
import time

import frappe
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes.api import ingest_machine_events, record_event, record_events
from foames.foames_mes.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, fake_request, make_machine, make_user

SECRET = "t0p-s3cret"


def signed_headers(body: bytes, timestamp=None, secret=SECRET):
	timestamp = int(time.time()) if timestamp is None else timestamp
	return {TIMESTAMP_HEADER: str(timestamp), SIGNATURE_HEADER: sign(secret, timestamp, body)}


class TestWebhook(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-WH", source_id="wh-press")
		settings = frappe.get_single("Machine Data Settings")
		settings.webhook_secret = SECRET
		settings.signature_tolerance_seconds = 300
		settings.save()

	def post(self, body, headers=None, user="Guest"):
		if not isinstance(body, bytes):
			body = json.dumps(body).encode()
		with as_user(user), fake_request(body, headers):
			return ingest_machine_events()

	def events_of(self, machine="T-WH"):
		return frappe.get_all(
			"Machine Event",
			{"machine": machine},
			["event_type", "source", "text", "timestamp"],
			order_by="creation asc",
		)

	def test_unsigned_guest_is_rejected(self):
		with self.assertRaises(frappe.AuthenticationError):
			self.post({"machine": "wh-press", "type": "Message", "text": "hi"})
		self.assertEqual(self.events_of(), [])

	def test_signed_guest_is_accepted_as_webhook(self):
		body = json.dumps({"events": [{"machine": "wh-press", "type": "Message", "text": "hi"}]}).encode()
		result = self.post(body, signed_headers(body))
		self.assertEqual(len(result["accepted"]), 1)
		self.assertEqual(result["rejected"], [])
		[event] = self.events_of()
		self.assertEqual((event.event_type, event.source, event.text), ("Message", "Webhook", "hi"))

	def test_wrong_secret_tampered_body_and_old_timestamp_are_rejected(self):
		body = json.dumps({"machine": "wh-press", "type": "Message"}).encode()
		with self.assertRaises(frappe.AuthenticationError):
			self.post(body, signed_headers(body, secret="other"))
		with self.assertRaises(frappe.AuthenticationError):
			self.post(body + b" ", signed_headers(body))
		with self.assertRaises(frappe.AuthenticationError):
			self.post(body, signed_headers(body, timestamp=int(time.time()) - 3600))
		with self.assertRaises(frappe.AuthenticationError):
			self.post(body, {SIGNATURE_HEADER: "abc"})

	def test_tolerance_comes_from_settings(self):
		frappe.db.set_single_value("Machine Data Settings", "signature_tolerance_seconds", 7200)
		body = json.dumps({"machine": "wh-press", "type": "Message"}).encode()
		result = self.post(body, signed_headers(body, timestamp=int(time.time()) - 3600))
		self.assertEqual(len(result["accepted"]), 1)

	def test_without_a_secret_no_guest_call_passes(self):
		settings = frappe.get_single("Machine Data Settings")
		settings.webhook_secret = None
		settings.save()
		body = json.dumps({"machine": "wh-press", "type": "Message"}).encode()
		with self.assertRaises(frappe.AuthenticationError):
			self.post(body, signed_headers(body, secret=""))

	def test_body_shapes(self):
		single = json.dumps({"machine": "wh-press", "type": "Message", "text": "one"}).encode()
		self.assertEqual(len(self.post(single, signed_headers(single))["accepted"]), 1)
		many = json.dumps(
			[{"machine": "wh-press", "type": "Message", "text": str(n)} for n in range(3)]
		).encode()
		self.assertEqual(len(self.post(many, signed_headers(many))["accepted"]), 3)
		wrapped = json.dumps({"events": {"machine": "wh-press"}}).encode()
		with self.assertRaises(frappe.ValidationError):
			self.post(wrapped, signed_headers(wrapped))
		bad = b"{not json"
		with self.assertRaises(frappe.ValidationError):
			self.post(bad, signed_headers(bad))

	def test_operator_may_post_unsigned(self):
		make_user("foames-wh-operator@example.com", "FoaMES Operator")
		make_user("foames-wh-quality@example.com", "FoaMES Quality")
		body = {"machine": "wh-press", "type": "Count", "value": 5}
		result = self.post(body, user="foames-wh-operator@example.com")
		self.assertEqual(len(result["accepted"]), 1)
		self.assertEqual(self.events_of()[0].source, "Manual")
		with self.assertRaises(frappe.AuthenticationError):
			self.post(body, user="foames-wh-quality@example.com")

	def test_guest_webhook_closes_downtime(self):
		# Processing runs with the webhook's authority: a machine coming back up must close its downtime.
		events = [
			{"machine": "wh-press", "type": "State", "state": "Down", "timestamp": "2026-10-20 08:00:00"},
			{"machine": "wh-press", "type": "State", "state": "Running", "timestamp": "2026-10-20 08:30:00"},
		]
		body = json.dumps({"events": events}).encode()
		result = self.post(body, signed_headers(body))
		self.assertEqual(len(result["accepted"]), 2)
		self.assertEqual(frappe.db.get_value("Machine", "T-WH", "status"), "Running")
		records = frappe.get_all("Downtime Record", {"machine": "T-WH"}, ["status", "duration_minutes"])
		self.assertEqual([(r.status, r.duration_minutes) for r in records], [("Closed", 30)])
		self.assertTrue(
			all(e.processed for e in frappe.get_all("Machine Event", {"machine": "T-WH"}, ["processed"]))
		)


class TestRecordEvents(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-REC", source_id="rec-1")

	def test_batch_reports_each_rejection_with_its_event(self):
		result = record_events(
			[
				{"machine": "rec-1", "type": "Message", "text": "ok"},
				{"machine": "rec-1", "type": "Count", "value": "many"},
				{"machine": "nobody", "type": "Message"},
				"not an object",
				{"machine": "rec-1", "type": "State", "state": "purple"},
			]
		)
		self.assertEqual(len(result["accepted"]), 1)
		reasons = [r["reason"] for r in result["rejected"]]
		self.assertEqual(len(reasons), 4)
		self.assertTrue(any("counter value" in r for r in reasons))
		self.assertTrue(any("no enabled machine" in r for r in reasons))
		self.assertTrue(any("must be an object" in r for r in reasons))
		self.assertTrue(any("unknown machine state" in r for r in reasons))
		# Rejections keep the order of the batch.
		self.assertEqual(result["rejected"][2]["event"], "not an object")
		self.assertEqual(result["rejected"][3]["event"]["state"], "purple")

	def test_empty_and_none_batches(self):
		self.assertEqual(record_events([]), {"accepted": [], "rejected": []})
		self.assertEqual(record_events(None), {"accepted": [], "rejected": []})

	def test_event_fields_are_stored(self):
		name = record_event(
			{
				"machine": "rec-1",
				"type": "Measurement",
				"name": "temp",
				"value": "71.5",
				"id": "m-1",
				"timestamp": "2026-10-20T08:00:00",
				"extra": {"unit": "C"},
			},
			source="OPC UA",
		)
		event = frappe.get_doc("Machine Event", name)
		self.assertEqual(
			(event.event_type, event.measurement_name, event.value), ("Measurement", "temp", 71.5)
		)
		self.assertEqual((event.source, event.event_key), ("OPC UA", "m-1"))
		self.assertEqual(get_datetime(event.timestamp), get_datetime("2026-10-20 08:00:00"))
		self.assertEqual(json.loads(event.payload)["extra"], {"unit": "C"})
		self.assertEqual(event.processed, 1)
		self.assertEqual(
			get_datetime(frappe.db.get_value("Machine", "T-REC", "last_seen")),
			get_datetime("2026-10-20 08:00:00"),
		)

	def test_duplicate_ids_are_rejected_only_when_given(self):
		record_events(
			[
				{"machine": "rec-1", "type": "Message", "id": "x"},
				{"machine": "rec-1", "type": "Message", "id": "x"},
			]
		)
		self.assertEqual(frappe.db.count("Machine Event", {"machine": "T-REC"}), 1)
		result = record_events(
			[{"machine": "rec-1", "type": "Message"}, {"machine": "rec-1", "type": "Message"}]
		)
		self.assertEqual(len(result["accepted"]), 2)

	def test_unix_and_zoned_timestamps_land_in_site_time(self):
		# Frappe compares stored datetimes with now_datetime() in the site's zone, so a Unix
		# timestamp of "now" must come back as "now" whatever the site's zone is.
		before = now_datetime()
		record_event({"machine": "rec-1", "type": "Message", "timestamp": time.time()})
		record_event(
			{"machine": "rec-1", "type": "Message", "timestamp": frappe.utils.now_datetime().isoformat()}
		)
		record_event({"machine": "rec-1", "type": "Message"})
		stamps = [
			get_datetime(e.timestamp)
			for e in frappe.get_all("Machine Event", {"machine": "T-REC"}, ["timestamp"])
		]
		for stamp in stamps:
			self.assertLess(abs((stamp - before).total_seconds()), 120, stamp)
		last_seen = get_datetime(frappe.db.get_value("Machine", "T-REC", "last_seen"))
		self.assertLess(abs((last_seen - before).total_seconds()), 120)

	def test_alarm_marks_the_machine_down_and_text_codes_are_kept(self):
		record_event({"machine": "rec-1", "type": "Alarm", "code": "E42", "timestamp": "2026-10-20 08:00:00"})
		self.assertEqual(frappe.db.get_value("Machine", "T-REC", "status"), "Down")
		event = frappe.get_all("Machine Event", {"machine": "T-REC"}, ["text", "value"])[0]
		self.assertEqual((event.text, event.value), ("E42", 1))
		self.assertEqual(frappe.db.count("Downtime Record", {"machine": "T-REC", "status": "Open"}), 1)

	def test_bad_processing_keeps_the_event_and_the_note(self):
		# A rollover of 0 with a reset is fine; force a processing error with a hook that raises.
		from foames.tests_helpers import extra_hooks

		with extra_hooks(foames_machine_event_handlers=["foames.foames_mes.test_api_ingest.explode"]):
			name = record_event({"machine": "rec-1", "type": "Message", "text": "boom"})
		event = frappe.get_doc("Machine Event", name)
		self.assertEqual(event.processed, 0)
		self.assertIn("handler exploded", event.processing_note)
		# The next event is processed normally.
		name = record_event({"machine": "rec-1", "type": "Message", "text": "fine"})
		self.assertEqual(frappe.db.get_value("Machine Event", name, "processed"), 1)


def explode(event, machine):
	raise RuntimeError("handler exploded")
