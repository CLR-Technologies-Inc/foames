# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Every path from a raw gateway message to a Machine Event dict, plus the webhook signature and the
counter arithmetic. No Frappe site needed."""

import unittest
from datetime import datetime, timedelta, timezone

from foames.foames_mes.counters import counter_delta, minutes_between
from foames.foames_mes.gateway.mapping import (
	EVENT_TYPES,
	MACHINE_STATES,
	STATE_ALIASES,
	EventError,
	mqtt_message_to_raw,
	normalise_event,
	normalise_state,
	parse_state_map,
	parse_timestamp,
	parse_topic,
)
from foames.foames_mes.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign, verify


class TestNormaliseEvent(unittest.TestCase):
	def test_common_fields(self):
		raw = {"machine": 7, "type": "Message", "message": "hello", "id": 42, "ts": 1_700_000_000}
		event = normalise_event(raw, source="MQTT")
		self.assertEqual(event["source_id"], "7")
		self.assertEqual(event["event_key"], "42")
		self.assertEqual(event["text"], "hello")
		self.assertEqual(event["source"], "MQTT")
		self.assertIs(event["payload"], raw)
		self.assertEqual(event["timestamp"], datetime(2023, 11, 14, 22, 13, 20))

	def test_source_id_key_is_an_alias_for_machine(self):
		event = normalise_event({"source_id": "L1", "type": "Message", "text": "x"})
		self.assertEqual(event["source_id"], "L1")

	def test_event_type_is_case_and_space_insensitive(self):
		for spelling in ("COUNT", "count", " Count "):
			event = normalise_event({"machine": "L1", "type": spelling, "value": 1})
			self.assertEqual(event["event_type"], "Count")
		event = normalise_event({"machine": "L1", "event_type": "state", "state": "Idle"})
		self.assertEqual(event["event_type"], "State")

	def test_missing_type_and_missing_id_and_missing_text(self):
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1"})
		event = normalise_event({"machine": "L1", "type": "Message"})
		self.assertIsNone(event["event_key"])
		self.assertIsNone(event["text"])

	def test_non_dict_is_rejected(self):
		for raw in ([1, 2], "event", None, 5):
			with self.assertRaises(EventError):
				normalise_event(raw)

	def test_default_source_is_webhook(self):
		self.assertEqual(normalise_event({"machine": "L1", "type": "Message"})["source"], "Webhook")

	def test_missing_timestamp_means_now(self):
		now = datetime.now(timezone.utc).replace(tzinfo=None)
		event = normalise_event({"machine": "L1", "type": "Message"})
		self.assertGreaterEqual(event["timestamp"], now - timedelta(seconds=5))
		self.assertLessEqual(event["timestamp"], now + timedelta(seconds=5))

	def test_count_counter_name_is_lowercased_and_value_coerced(self):
		event = normalise_event({"machine": "L1", "type": "Count", "counter": "Scrap", "value": "12"})
		self.assertEqual((event["counter_name"], event["counter_value"]), ("scrap", 12.0))
		event = normalise_event({"machine": "L1", "type": "Count", "name": "Rework", "value": 3})
		self.assertEqual(event["counter_name"], "rework")

	def test_count_needs_a_numeric_value(self):
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "Count"})
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "Count", "value": None})

	def test_measurement_name_and_value(self):
		event = normalise_event({"machine": "L1", "type": "Measurement", "name": " temp ", "value": "71.5"})
		self.assertEqual((event["measurement_name"], event["value"]), ("temp", 71.5))
		event = normalise_event(
			{"machine": "L1", "type": "Measurement", "measurement": "pressure", "value": 2}
		)
		self.assertEqual(event["measurement_name"], "pressure")

	def test_measurement_needs_name_and_number(self):
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "Measurement", "value": 1})
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "Measurement", "name": "  ", "value": 1})
		with self.assertRaises(EventError):
			normalise_event({"machine": "L1", "type": "Measurement", "name": "t", "value": "hot"})

	def test_alarm_with_numeric_code(self):
		event = normalise_event({"machine": "L1", "type": "Alarm", "code": 42})
		self.assertEqual((event["value"], event["text"]), (42.0, "42"))

	def test_alarm_with_text_code_is_accepted(self):
		# The docs promise `code` or `value` plus `text`; PLC alarm codes are often text.
		event = normalise_event({"machine": "L1", "type": "Alarm", "code": "E42", "text": "Door open"})
		self.assertEqual((event["value"], event["text"]), (1.0, "Door open"))
		event = normalise_event({"machine": "L1", "type": "Alarm", "code": "E42"})
		self.assertEqual((event["value"], event["text"]), (1.0, "E42"))

	def test_alarm_value_wins_over_code(self):
		event = normalise_event({"machine": "L1", "type": "Alarm", "value": 7, "code": "E42"})
		self.assertEqual((event["value"], event["text"]), (7.0, "E42"))

	def test_alarm_with_nothing_is_on(self):
		event = normalise_event({"machine": "L1", "type": "Alarm"})
		self.assertEqual((event["value"], event["text"]), (1.0, ""))

	def test_alarm_zero_value_is_kept(self):
		event = normalise_event({"machine": "L1", "type": "Alarm", "value": 0})
		self.assertEqual(event["value"], 0.0)

	def test_state_from_value_key(self):
		event = normalise_event({"machine": "L1", "type": "State", "value": "changeover"})
		self.assertEqual(event["state"], "Setup")

	def test_every_alias_maps_to_a_known_state(self):
		for alias, state in STATE_ALIASES.items():
			self.assertIn(state, MACHINE_STATES)
			self.assertEqual(normalise_state(alias), state)
			self.assertEqual(normalise_state(alias.upper()), state)

	def test_canonical_states_pass_untouched(self):
		for state in MACHINE_STATES:
			self.assertEqual(normalise_state(state), state)
			self.assertEqual(normalise_state(f"  {state} "), state)

	def test_state_errors(self):
		with self.assertRaises(EventError):
			normalise_state(None)
		with self.assertRaises(EventError):
			normalise_state("")
		with self.assertRaises(EventError):
			normalise_state(3)

	def test_event_types_match_the_doctype_options(self):
		self.assertEqual(EVENT_TYPES, ("State", "Count", "Measurement", "Alarm", "Message"))


class TestParseTimestamp(unittest.TestCase):
	def test_float_seconds(self):
		self.assertEqual(parse_timestamp(1_700_000_000.5), datetime(2023, 11, 14, 22, 13, 20, 500000))

	def test_naive_iso_is_taken_as_utc(self):
		self.assertEqual(parse_timestamp("2026-10-30 02:00:00"), datetime(2026, 10, 30, 2, 0, 0))

	def test_negative_offset(self):
		self.assertEqual(parse_timestamp("2026-10-30T02:00:00-05:00"), datetime(2026, 10, 30, 7, 0, 0))

	def test_surrounding_whitespace(self):
		self.assertEqual(parse_timestamp(" 2026-10-30T02:00:00Z "), datetime(2026, 10, 30, 2, 0, 0))

	def test_bad_text(self):
		for value in ("yesterday", "", "2026-13-45"):
			with self.assertRaises(EventError):
				parse_timestamp(value)


class TestTopics(unittest.TestCase):
	def test_prefix_with_slashes_and_nested_source_ids(self):
		self.assertEqual(parse_topic("plant/a/line1/press/count", "/plant/a/"), ("line1/press", "count"))
		self.assertEqual(parse_topic("plant/a/press/count", "plant/a"), ("press", "count"))

	def test_too_short_topics(self):
		self.assertIsNone(parse_topic("foames/press", "foames"))
		self.assertIsNone(parse_topic("foames", "foames"))
		self.assertIsNone(parse_topic("", "foames"))

	def test_empty_prefix_takes_the_whole_topic(self):
		self.assertEqual(parse_topic("press/count", ""), ("press", "count"))
		self.assertIsNone(parse_topic("count", ""))

	def test_prefix_must_match_whole_segments(self):
		self.assertIsNone(parse_topic("foamesx/press/count", "foames"))


class TestMQTTMessages(unittest.TestCase):
	def test_bare_number_and_bool_payloads(self):
		raw = mqtt_message_to_raw("f/press/count", b"42", "f")
		self.assertEqual(raw["value"], 42)
		raw = mqtt_message_to_raw("f/press/state", b"true", "f")
		self.assertIs(raw["value"], True)

	def test_json_array_becomes_a_value(self):
		raw = mqtt_message_to_raw("f/press/count", b"[1, 2]", "f")
		self.assertEqual(raw["value"], [1, 2])

	def test_payload_fields_win_over_the_topic(self):
		raw = mqtt_message_to_raw(
			"f/press/count", b'{"machine": "press-2", "type": "Measurement", "value": 1}', "f"
		)
		self.assertEqual((raw["machine"], raw["type"]), ("press-2", "Measurement"))

	def test_invalid_utf8_is_replaced_not_fatal(self):
		raw = mqtt_message_to_raw("f/press/message", b"\xff\xfe", "f")
		self.assertIn("�", raw["value"])

	def test_string_payload(self):
		raw = mqtt_message_to_raw("f/press/state", "idle", "f")
		self.assertEqual(normalise_event(raw, "MQTT")["state"], "Idle")

	def test_wrong_prefix_is_an_event_error(self):
		with self.assertRaises(EventError):
			mqtt_message_to_raw("other/press/count", b"1", "f")

	def test_full_round_trip_to_event(self):
		raw = mqtt_message_to_raw(
			"f/line1/press/count", b'{"value": 10, "counter": "scrap", "id": "x1"}', "f"
		)
		event = normalise_event(raw, "MQTT")
		self.assertEqual(event["source_id"], "line1/press")
		self.assertEqual(
			(event["counter_name"], event["counter_value"], event["event_key"]), ("scrap", 10.0, "x1")
		)


class TestStateMap(unittest.TestCase):
	def test_lines_with_spaces_and_blanks(self):
		mapping = parse_state_map(" 1 = Running \n\n2=Down\nnonsense\n=Idle\n3 = Setup = x")
		self.assertEqual(mapping, {"1": "Running", "2": "Down", "": "Idle", "3": "Setup = x"})

	def test_empty(self):
		self.assertEqual(parse_state_map(None), {})
		self.assertEqual(parse_state_map(""), {})


class TestSigning(unittest.TestCase):
	def test_str_and_bytes_bodies_sign_the_same(self):
		self.assertEqual(sign("s", 1, "abc"), sign("s", 1, b"abc"))
		self.assertEqual(sign("s", "1", b"abc"), sign("s", 1, b"abc"))

	def test_signature_is_hex_sha256(self):
		signature = sign("s", 1, b"")
		self.assertEqual(len(signature), 64)
		int(signature, 16)

	def test_case_and_whitespace_of_the_header_do_not_matter(self):
		body = b"{}"
		signature = sign("s", 100, body)
		self.assertTrue(verify("s", 100, body, "  " + signature.upper() + "\n", now=100))
		self.assertTrue(verify("s", "100", body, signature, now=100))

	def test_missing_signature(self):
		self.assertFalse(verify("s", 100, b"{}", None, now=100))
		self.assertFalse(verify("s", 100, b"{}", "", now=100))
		self.assertFalse(verify("s", None, b"{}", sign("s", 100, b"{}"), now=100))

	def test_tolerance_is_symmetric_and_inclusive(self):
		body = b"{}"
		signature = sign("s", 1000, body)
		self.assertTrue(verify("s", 1000, body, signature, tolerance_seconds=300, now=1300))
		self.assertTrue(verify("s", 1000, body, signature, tolerance_seconds=300, now=700))
		self.assertFalse(verify("s", 1000, body, signature, tolerance_seconds=300, now=1301))
		self.assertFalse(verify("s", 1000, body, signature, tolerance_seconds=300, now=699))

	def test_zero_tolerance_disables_the_replay_check(self):
		body = b"{}"
		self.assertTrue(verify("s", 1000, body, sign("s", 1000, body), tolerance_seconds=0, now=9_999_999))

	def test_uses_wall_clock_when_now_is_not_given(self):
		import time

		ts = int(time.time())
		self.assertTrue(verify("s", ts, b"x", sign("s", ts, b"x")))
		self.assertFalse(verify("s", ts - 10_000, b"x", sign("s", ts - 10_000, b"x")))

	def test_header_names(self):
		self.assertEqual((SIGNATURE_HEADER, TIMESTAMP_HEADER), ("X-FoaMES-Signature", "X-FoaMES-Timestamp"))


class TestCounters(unittest.TestCase):
	def test_equal_readings_count_zero(self):
		self.assertEqual(counter_delta(100, 100), 0.0)

	def test_rollover_boundaries(self):
		self.assertEqual(counter_delta(10000, 0, rollover=10000), 0.0)  # counts up to, then from zero
		self.assertEqual(counter_delta(9999, 0, rollover=10000), 1.0)
		self.assertEqual(
			counter_delta(10001, 5, rollover=10000), 0.0
		)  # previous beyond the rollover: a reset
		self.assertEqual(counter_delta(5, 3, rollover=0), 0.0)
		self.assertEqual(counter_delta(5, 3, rollover=-1), 0.0)

	def test_float_readings(self):
		self.assertAlmostEqual(counter_delta(1.5, 4.25), 2.75)
		self.assertAlmostEqual(counter_delta(99.5, 0.5, rollover=100), 1.0)

	def test_result_is_a_float(self):
		self.assertIsInstance(counter_delta(1, 2), float)
		self.assertIsInstance(counter_delta(None, 2), float)

	def test_minutes_between(self):
		start = datetime(2026, 1, 1, 8, 0, 0)
		self.assertEqual(minutes_between(start, start + timedelta(minutes=90)), 90.0)
		self.assertEqual(minutes_between(start, start + timedelta(seconds=30)), 0.5)
		self.assertEqual(minutes_between(start, start), 0.0)
		self.assertEqual(minutes_between(start + timedelta(hours=1), start), 0.0)


if __name__ == "__main__":
	unittest.main()
