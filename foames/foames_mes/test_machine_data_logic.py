# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json
import unittest
from datetime import datetime

from foames.foames_mes.counters import counter_delta
from foames.foames_mes.gateway.mapping import (
	EventError,
	mqtt_message_to_raw,
	normalise_event,
	parse_timestamp,
	parse_topic,
)
from foames.foames_mes.signing import sign, verify


class TestCounterDelta(unittest.TestCase):
	def test_first_reading_invents_nothing(self):
		self.assertEqual(counter_delta(None, 500), 0)

	def test_normal_increment(self):
		self.assertEqual(counter_delta(500, 512), 12)

	def test_reset_without_rollover_invents_nothing(self):
		self.assertEqual(counter_delta(500, 3), 0)

	def test_rollover(self):
		self.assertEqual(counter_delta(9998, 3, rollover=10000), 5)

	def test_out_of_order_reading_is_zero(self):
		self.assertEqual(counter_delta(512, 500), 0)


class TestSigning(unittest.TestCase):
	def test_round_trip_and_tamper(self):
		body = b'{"events": []}'
		sig = sign("secret", 1700000000, body)
		self.assertTrue(verify("secret", 1700000000, body, sig, now=1700000010))
		self.assertFalse(verify("secret", 1700000000, b'{"events": [1]}', sig, now=1700000010))
		self.assertFalse(verify("other", 1700000000, body, sig, now=1700000010))

	def test_replay_outside_tolerance(self):
		body = b"{}"
		sig = sign("secret", 1700000000, body)
		self.assertFalse(verify("secret", 1700000000, body, sig, tolerance_seconds=300, now=1700001000))
		self.assertFalse(verify("secret", "not-a-time", body, sig))


class TestEventMapping(unittest.TestCase):
	def test_state_aliases(self):
		event = normalise_event({"machine": "L1", "type": "state", "state": "fault", "ts": 1700000000})
		self.assertEqual((event["event_type"], event["state"]), ("State", "Down"))
		self.assertEqual(event["timestamp"], datetime(2023, 11, 14, 22, 13, 20))

	def test_count_defaults_to_good(self):
		event = normalise_event({"machine": "L1", "type": "Count", "value": "1200"})
		self.assertEqual((event["counter_name"], event["counter_value"]), ("good", 1200.0))

	def test_errors_are_plain(self):
		with self.assertRaises(EventError):
			normalise_event({"type": "Count", "value": 1})
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "Temperature"})
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "Count", "value": "many"})
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "State", "state": "purple"})

	def test_iso_timestamp_to_utc(self):
		self.assertEqual(parse_timestamp("2026-10-30T02:00:00+02:00"), datetime(2026, 10, 30, 0, 0, 0))
		self.assertEqual(parse_timestamp("2026-10-30T02:00:00Z"), datetime(2026, 10, 30, 2, 0, 0))

	def test_mqtt_topic_and_payload(self):
		self.assertEqual(parse_topic("foames/line1/press/count", "foames"), ("line1/press", "count"))
		self.assertIsNone(parse_topic("other/line1/count", "foames"))
		raw = mqtt_message_to_raw("foames/press/count", json.dumps({"value": 42}).encode(), "foames")
		self.assertEqual((raw["machine"], raw["type"], raw["value"]), ("press", "count", 42))
		raw = mqtt_message_to_raw("foames/press/state", b"Running", "foames")
		self.assertEqual(normalise_event(raw, "MQTT")["state"], "Running")
