# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Sparkplug B decoder, topics, alias book and metric-to-event rules in depth. Builds on the small
protobuf encoder in test_sparkplug. No Frappe site needed."""

import struct
import unittest
from types import SimpleNamespace

from foames.foames_mes.gateway.mapping import EventError, normalise_event
from foames.foames_mes.gateway.sparkplug import (
	BOOLEAN,
	DATETIME,
	DOUBLE,
	FLOAT,
	INT8,
	INT16,
	INT32,
	INT64,
	MESSAGE_TYPES,
	NAMESPACE,
	STRING,
	UINT8,
	UINT32,
	UINT64,
	AliasBook,
	Metric,
	Payload,
	Topic,
	decode_metric,
	decode_payload,
	is_reserved_metric,
	match_row,
	message_to_raw_events,
	metric_to_raw,
	parse_sparkplug_topic,
)
from foames.foames_mes.test_sparkplug import field_bytes, field_varint, metric, payload, varint


def field_fixed32(number: int, value: float) -> bytes:
	return varint((number << 3) | 5) + struct.pack("<f", value)


def raw_metric(*fields: bytes) -> bytes:
	"""A metric message from already-encoded fields, for cases the helper does not cover."""
	return field_bytes(2, b"".join(fields))


class TestVarintsAndWireTypes(unittest.TestCase):
	def test_multi_byte_varint(self):
		data = payload(metric("m", datatype=UINT64, value=300_000_000_000))
		self.assertEqual(decode_payload(data).metrics[0].value, 300_000_000_000)

	def test_unknown_fields_are_skipped(self):
		# Field 8 (metadata) and 9 (properties) are length-delimited; field 99 is a varint nobody knows.
		m = raw_metric(
			field_bytes(1, b"x"),
			field_bytes(8, b"\x08\x01"),
			field_bytes(9, b""),
			field_varint(99, 5),
			field_varint(4, UINT32),
			field_varint(10, 7),
		)
		decoded = decode_payload(field_varint(1, 1) + m)
		self.assertEqual((decoded.metrics[0].name, decoded.metrics[0].value), ("x", 7))

	def test_fixed32_and_fixed64_values(self):
		m = raw_metric(field_bytes(1, b"f"), field_varint(4, FLOAT), field_fixed32(12, 1.5))
		self.assertEqual(decode_payload(m).metrics[0].value, 1.5)
		m = raw_metric(
			field_bytes(1, b"d"), field_varint(4, DOUBLE), varint((13 << 3) | 1) + struct.pack("<d", -2.25)
		)
		self.assertEqual(decode_payload(m).metrics[0].value, -2.25)

	def test_unsupported_wire_type_is_rejected(self):
		with self.assertRaises(EventError):
			decode_payload(bytes([(1 << 3) | 3, 0]))  # start-group

	def test_overlong_varint_is_rejected(self):
		with self.assertRaises(EventError):
			decode_payload(bytes([0x08]) + b"\xff" * 11)

	def test_truncated_fixed_field_is_rejected(self):
		m = raw_metric(field_bytes(1, b"d"), varint((13 << 3) | 1) + b"\x00\x00")
		with self.assertRaises(EventError):
			decode_payload(m)

	def test_truncated_varint_is_rejected(self):
		with self.assertRaises(EventError):
			decode_payload(b"\x08\xff")

	def test_empty_payload(self):
		decoded = decode_payload(b"")
		self.assertEqual((decoded.timestamp, decoded.seq, decoded.metrics), (None, None, []))


class TestMetricValues(unittest.TestCase):
	def decode_one(self, data: bytes) -> Metric:
		return decode_payload(data).metrics[0]

	def test_signed_integers(self):
		self.assertEqual(self.decode_one(metric("a", datatype=INT8, value=-1)).value, -1)
		self.assertEqual(self.decode_one(metric("a", datatype=INT8, value=127)).value, 127)
		self.assertEqual(self.decode_one(metric("a", datatype=INT8, value=200)).value, -56)
		self.assertEqual(self.decode_one(metric("a", datatype=INT16, value=-30000)).value, -30000)
		self.assertEqual(
			self.decode_one(metric("a", datatype=INT32, value=-2_000_000_000)).value, -2_000_000_000
		)
		data = raw_metric(field_bytes(1, b"a"), field_varint(4, INT64), field_varint(11, (1 << 64) - 5))
		self.assertEqual(self.decode_one(data).value, -5)

	def test_unsigned_integers_are_not_sign_converted(self):
		self.assertEqual(self.decode_one(metric("a", datatype=UINT8, value=200)).value, 200)
		self.assertEqual(
			self.decode_one(metric("a", datatype=UINT32, value=4_000_000_000)).value, 4_000_000_000
		)
		data = raw_metric(field_bytes(1, b"a"), field_varint(4, UINT64), field_varint(11, (1 << 64) - 5))
		self.assertEqual(self.decode_one(data).value, (1 << 64) - 5)

	def test_datetime_is_converted_to_seconds(self):
		data = raw_metric(
			field_bytes(1, b"t"), field_varint(4, DATETIME), field_varint(11, 1_700_000_000_000)
		)
		self.assertEqual(self.decode_one(data).value, 1_700_000_000.0)

	def test_boolean_false_and_true(self):
		self.assertIs(self.decode_one(metric("b", datatype=BOOLEAN, value=False)).value, False)
		self.assertIs(self.decode_one(metric("b", datatype=BOOLEAN, value=True)).value, True)

	def test_bytes_value_and_historical_flag(self):
		data = raw_metric(field_bytes(1, b"raw"), field_varint(5, 1), field_bytes(16, b"\x01\x02"))
		m = self.decode_one(data)
		self.assertEqual(m.value, b"\x01\x02")
		self.assertTrue(m.is_historical)

	def test_invalid_utf8_name_does_not_crash(self):
		data = raw_metric(field_bytes(1, b"\xff\xfe"), field_varint(4, UINT32), field_varint(10, 1))
		self.assertIn("�", self.decode_one(data).name)

	def test_null_metric_keeps_no_value(self):
		m = self.decode_one(metric("n", datatype=STRING, is_null=True))
		self.assertTrue(m.is_null)
		self.assertIsNone(m.value)

	def test_decode_metric_directly(self):
		m = decode_metric(
			field_bytes(1, b"a")
			+ field_varint(2, 3)
			+ field_varint(3, 99)
			+ field_varint(4, UINT32)
			+ field_varint(10, 1)
		)
		self.assertEqual((m.name, m.alias, m.timestamp, m.datatype, m.value), ("a", 3, 99, UINT32, 1))

	def test_payload_dataclass_defaults(self):
		self.assertEqual(Payload().metrics, [])
		self.assertIsNone(Metric().value)


class TestTopics(unittest.TestCase):
	def test_every_message_type_parses(self):
		for message_type in MESSAGE_TYPES:
			topic = parse_sparkplug_topic(f"{NAMESPACE}/G/{message_type}/E")
			self.assertEqual(topic.message_type, message_type)

	def test_device_id_may_contain_slashes(self):
		topic = parse_sparkplug_topic("spBv1.0/G/DDATA/E/line1/press")
		self.assertEqual(topic.device, "line1/press")
		self.assertEqual(topic.machine_source_id, "line1/press")

	def test_wrong_namespace_or_unknown_type(self):
		self.assertIsNone(parse_sparkplug_topic("spAv1.0/G/DDATA/E/D"))
		self.assertIsNone(parse_sparkplug_topic("spBv1.0/G/XDATA/E/D"))
		self.assertIsNone(parse_sparkplug_topic("spBv1.0/G/DDATA"))
		self.assertIsNone(parse_sparkplug_topic(""))

	def test_topic_is_hashable_and_comparable(self):
		a = parse_sparkplug_topic("spBv1.0/G/DDATA/E/D")
		b = Topic("G", "DDATA", "E", "D")
		self.assertEqual(a, b)
		self.assertEqual(len({a, b}), 1)


class TestAliasBook(unittest.TestCase):
	def test_aliases_are_scoped_per_device(self):
		book = AliasBook()
		book.learn(Topic("G", "DBIRTH", "E", "P1"), Payload(metrics=[Metric(name="good", alias=1)]))
		book.learn(Topic("G", "DBIRTH", "E", "P2"), Payload(metrics=[Metric(name="scrap", alias=1)]))
		self.assertEqual(book.resolve(Topic("G", "DDATA", "E", "P1"), Metric(alias=1)), "good")
		self.assertEqual(book.resolve(Topic("G", "DDATA", "E", "P2"), Metric(alias=1)), "scrap")
		self.assertIsNone(book.resolve(Topic("G", "DDATA", "E", "P3"), Metric(alias=1)))
		self.assertIsNone(book.resolve(Topic("G", "NDATA", "E"), Metric(alias=1)))

	def test_name_wins_over_alias(self):
		book = AliasBook()
		self.assertEqual(book.resolve(Topic("G", "DDATA", "E", "P1"), Metric(name="x", alias=5)), "x")

	def test_no_name_no_alias(self):
		self.assertIsNone(AliasBook().resolve(Topic("G", "DDATA", "E", "P1"), Metric()))

	def test_rebirth_replaces_aliases(self):
		book = AliasBook()
		topic = Topic("G", "DBIRTH", "E", "P1")
		book.learn(topic, Payload(metrics=[Metric(name="good", alias=1)]))
		book.learn(topic, Payload(metrics=[Metric(name="total", alias=1)]))
		self.assertEqual(book.resolve(Topic("G", "DDATA", "E", "P1"), Metric(alias=1)), "total")

	def test_metrics_without_alias_or_name_are_not_learned(self):
		book = AliasBook()
		book.learn(Topic("G", "DBIRTH", "E", "P1"), Payload(metrics=[Metric(name="x"), Metric(alias=2)]))
		self.assertIsNone(book.resolve(Topic("G", "DDATA", "E", "P1"), Metric(alias=2)))

	def test_devices_of_lists_devices_not_the_node(self):
		book = AliasBook()
		book.learn(Topic("G", "NBIRTH", "E"), Payload(metrics=[Metric(name="bdSeq", alias=0)]))
		book.learn(Topic("G", "DBIRTH", "E", "P1"), Payload(metrics=[Metric(name="x", alias=1)]))
		book.learn(Topic("G", "DBIRTH", "E2", "P9"), Payload(metrics=[Metric(name="x", alias=1)]))
		self.assertEqual(book.devices_of("G", "E"), ["P1"])
		self.assertEqual(book.devices_of("G", "nope"), [])


def row(**overrides):
	values = {
		"source": "Sparkplug B",
		"node_id": "E/P1/PLC/Count",
		"machine": "PRESS-1",
		"machine_source_id": "press-1",
		"event_type": "Count",
		"name_or_counter": None,
		"state_map": None,
	}
	values.update(overrides)
	return SimpleNamespace(**values)


class TestMatchRow(unittest.TestCase):
	topic = Topic("G", "DDATA", "E", "P1")

	def test_every_path_form_matches(self):
		for node_id in ("G/E/P1/PLC/Count", "G/E/PLC/Count", "E/P1/PLC/Count", "E/PLC/Count"):
			self.assertIsNotNone(match_row([row(node_id=node_id)], self.topic, "PLC/Count"), node_id)

	def test_other_sources_and_other_metrics_do_not_match(self):
		self.assertIsNone(match_row([row(source="OPC UA")], self.topic, "PLC/Count"))
		self.assertIsNone(match_row([row()], self.topic, "PLC/Other"))
		self.assertIsNone(match_row([row(node_id="X/P1/PLC/Count")], self.topic, "PLC/Count"))
		self.assertIsNone(match_row(None, self.topic, "PLC/Count"))

	def test_node_level_topic_has_no_device_forms(self):
		topic = Topic("G", "NDATA", "E")
		self.assertIsNotNone(match_row([row(node_id="E/PLC/Count")], topic, "PLC/Count"))
		self.assertIsNone(match_row([row(node_id="E/None/PLC/Count")], topic, "PLC/Count"))

	def test_first_matching_row_wins(self):
		rows = [row(event_type="Count"), row(event_type="Measurement")]
		self.assertEqual(match_row(rows, self.topic, "PLC/Count").event_type, "Count")


class TestMetricToRaw(unittest.TestCase):
	topic = Topic("G", "DDATA", "E", "P1")
	payload = Payload(timestamp=1_700_000_000_000)

	def raw(self, name, value, rows=None, timestamp=None, datatype=None):
		return metric_to_raw(
			self.topic,
			name,
			Metric(name=name, value=value, timestamp=timestamp, datatype=datatype),
			self.payload,
			rows,
		)

	def test_timestamps_and_ids(self):
		event = self.raw("good", 1)
		self.assertEqual(event["timestamp"], 1_700_000_000.0)
		self.assertEqual(event["id"], "sp:G/E/P1:1700000000000:good")
		event = self.raw("good", 1, timestamp=1_700_000_005_000)
		self.assertEqual(event["timestamp"], 1_700_000_005.0)
		self.assertEqual(event["id"], "sp:G/E/P1:1700000005000:good")

	def test_no_timestamp_means_no_id(self):
		# Two untimestamped readings must not collide on the dedupe key.
		event = metric_to_raw(self.topic, "good", Metric(name="good", value=1), Payload(), None)
		self.assertIsNone(event["timestamp"])
		self.assertNotIn("id", event)
		normalise_event(event, "MQTT")

	def test_null_and_none_values_give_nothing(self):
		self.assertIsNone(self.raw("good", None))
		self.assertIsNone(
			metric_to_raw(self.topic, "good", Metric(name="good", value=1, is_null=True), self.payload)
		)

	def test_convention_counters(self):
		for name in (
			"good",
			"scrap",
			"count",
			"total",
			"parts",
			"reject",
			"bad",
			"ng",
			"Line/Good",
			"Line/Scrap",
		):
			event = self.raw(name, 5)
			self.assertEqual(event["type"], "Count", name)
			self.assertEqual(event["counter"], name.rsplit("/", 1)[-1].lower())
			self.assertEqual(event["value"], 5)
		event = self.raw("Line/count/Rework", 2)
		self.assertEqual((event["type"], event["counter"]), ("Count", "rework"))
		event = self.raw("count/rework", 2)
		self.assertEqual((event["type"], event["counter"]), ("Count", "rework"))

	def test_convention_state(self):
		event = self.raw("Line/State", "run")
		self.assertEqual((event["type"], event["state"], event["machine"]), ("State", "run", "P1"))
		self.assertEqual(normalise_event(event, "MQTT")["state"], "Running")

	def test_convention_alarm(self):
		event = self.raw("Line/alarm", 42)
		self.assertEqual((event["type"], event["value"], event["text"]), ("Alarm", 42, "42"))
		event = self.raw("alarm", "E42")
		self.assertEqual((event["value"], event["text"]), (1, "E42"))
		event = self.raw("alarm", True)
		self.assertEqual(event["value"], True)
		self.assertEqual(normalise_event(event, "MQTT")["value"], 1.0)

	def test_convention_message(self):
		event = self.raw("Line/message", "hello")
		self.assertEqual((event["type"], event["text"]), ("Message", "hello"))
		event = self.raw("message", 5)
		self.assertEqual(event["text"], "5")

	def test_convention_measurement_keeps_full_name(self):
		event = self.raw("Line/Zone1/Temperature", 71.5)
		self.assertEqual(
			(event["type"], event["name"], event["value"]), ("Measurement", "Line/Zone1/Temperature", 71.5)
		)

	def test_convention_skips_what_it_cannot_place(self):
		self.assertIsNone(self.raw("Line/ready", True))
		self.assertIsNone(self.raw("Line/label", "A"))
		self.assertIsNone(self.raw("Line/blob", b"\x00"))

	def test_reserved_metrics_are_skipped_by_convention(self):
		for name in (
			"bdSeq",
			"Node Control/Rebirth",
			"Node Control/Reboot",
			"Device Control/Scan Rate",
			"Properties/Hardware Make",
		):
			self.assertTrue(is_reserved_metric(name))
			self.assertIsNone(self.raw(name, 1), name)
		self.assertFalse(is_reserved_metric("Line/good"))

	def test_reserved_metric_can_still_be_mapped_by_a_row(self):
		rows = [row(node_id="E/P1/bdSeq", event_type="Measurement", name_or_counter="birth-seq")]
		event = self.raw("bdSeq", 3, rows)
		self.assertEqual((event["type"], event["name"], event["value"]), ("Measurement", "birth-seq", 3))

	def test_row_mapping_for_every_event_type(self):
		event = self.raw("PLC/Count", 10, [row(event_type="Count", name_or_counter="Scrap")])
		self.assertEqual(
			(event["machine"], event["type"], event["counter"], event["value"]),
			("press-1", "Count", "Scrap", 10),
		)
		event = self.raw("PLC/Count", 10, [row(event_type="Count")])
		self.assertEqual(event["counter"], "good")
		event = self.raw("PLC/Count", 1.5, [row(event_type="Measurement")])
		self.assertEqual((event["name"], event["value"]), ("PLC/Count", 1.5))
		event = self.raw("PLC/Count", 1.5, [row(event_type="Measurement", name_or_counter="temp")])
		self.assertEqual(event["name"], "temp")
		event = self.raw("PLC/Count", 2, [row(event_type="State", state_map="1=Running\n2=Down")])
		self.assertEqual(event["state"], "Down")
		event = self.raw("PLC/Count", "Idle", [row(event_type="State", state_map="1=Running")])
		self.assertEqual(event["state"], "Idle")  # unmapped values pass through for the alias table
		event = self.raw("PLC/Count", 9, [row(event_type="Alarm")])
		self.assertEqual((event["type"], event["value"]), ("Alarm", 9))
		event = self.raw("PLC/Count", 9, [row(event_type="Message")])
		self.assertEqual((event["type"], event["text"]), ("Message", "9"))

	def test_row_without_source_id_attribute_uses_machine(self):
		plain = SimpleNamespace(
			source="Sparkplug B",
			node_id="E/P1/PLC/Count",
			machine="PRESS-1",
			event_type="Count",
			name_or_counter=None,
			state_map=None,
		)
		self.assertEqual(self.raw("PLC/Count", 1, [plain])["machine"], "PRESS-1")

	def test_row_mapping_ignores_the_convention(self):
		# A metric named "state" mapped as a Count by a row is a Count.
		event = self.raw("PLC/Count", 5, [row(event_type="Count")])
		self.assertEqual(event["type"], "Count")

	def test_node_level_metric_belongs_to_the_edge_node(self):
		event = metric_to_raw(Topic("G", "NDATA", "E"), "good", Metric(name="good", value=1), self.payload)
		self.assertEqual(event["machine"], "E")
		self.assertEqual(event["id"], "sp:G/E/:1700000000000:good")


class TestMessages(unittest.TestCase):
	def test_commands_yield_nothing(self):
		for message_type in ("NCMD", "DCMD"):
			topic = Topic("G", message_type, "E", "P1")
			events = message_to_raw_events(
				topic, Payload(metrics=[Metric(name="good", value=1)]), AliasBook()
			)
			self.assertEqual(events, [])

	def test_birth_learns_and_records(self):
		aliases = AliasBook()
		topic = Topic("G", "NBIRTH", "E")
		births = Payload(
			timestamp=1,
			metrics=[Metric(name="bdSeq", alias=0, value=0), Metric(name="good", alias=1, value=10)],
		)
		events = message_to_raw_events(topic, births, aliases)
		self.assertEqual([(e["type"], e["machine"]) for e in events], [("Count", "E")])
		data = message_to_raw_events(
			Topic("G", "NDATA", "E"), Payload(timestamp=2, metrics=[Metric(alias=1, value=11)]), aliases
		)
		self.assertEqual(data[0]["value"], 11)

	def test_death_timestamp(self):
		events = message_to_raw_events(
			Topic("G", "DDEATH", "E", "P1"), Payload(timestamp=1_700_000_000_000), AliasBook()
		)
		self.assertEqual(
			events, [{"machine": "P1", "type": "State", "state": "Unknown", "timestamp": 1_700_000_000.0}]
		)
		events = message_to_raw_events(Topic("G", "DDEATH", "E", "P1"), Payload(), AliasBook())
		self.assertIsNone(events[0]["timestamp"])
		normalise_event(events[0], "MQTT")

	def test_death_ignores_metrics(self):
		payload = Payload(metrics=[Metric(name="good", value=1)])
		events = message_to_raw_events(Topic("G", "NDEATH", "E"), payload, AliasBook())
		self.assertEqual([e["type"] for e in events], ["State"])

	def test_data_events_pass_common_validation(self):
		aliases = AliasBook()
		data = Payload(
			timestamp=1_700_000_000_000,
			metrics=[
				Metric(name="Line/state", value="Down"),
				Metric(name="Line/good", value=5),
				Metric(name="Line/temp", value=1.5),
				Metric(name="Line/alarm", value="E1"),
				Metric(name="Line/message", value="ok"),
			],
		)
		events = message_to_raw_events(Topic("G", "DDATA", "E", "P1"), data, aliases)
		self.assertEqual(len(events), 5)
		for raw in events:
			normalised = normalise_event(raw, "MQTT")
			self.assertEqual(normalised["source_id"], "P1")
			self.assertTrue(normalised["event_key"].startswith("sp:G/E/P1:"))

	def test_decoded_bytes_end_to_end(self):
		data = decode_payload(
			payload(metric("Line/good", datatype=UINT64, value=77, timestamp=1_700_000_001_000))
		)
		events = message_to_raw_events(Topic("G", "DDATA", "E", "P1"), data, AliasBook())
		self.assertEqual(
			(events[0]["counter"], events[0]["value"], events[0]["timestamp"]), ("good", 77, 1_700_000_001.0)
		)


if __name__ == "__main__":
	unittest.main()
