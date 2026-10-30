# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import struct
import unittest

from foames.foames_mes.gateway.mapping import EventError, normalise_event
from foames.foames_mes.gateway.sparkplug import (
	BOOLEAN,
	DOUBLE,
	INT32,
	STRING,
	UINT64,
	AliasBook,
	Topic,
	decode_payload,
	message_to_raw_events,
	parse_sparkplug_topic,
)

# A minimal protobuf encoder, enough to build Sparkplug B payloads for the decoder under test.


def varint(value: int) -> bytes:
	out = bytearray()
	while True:
		byte = value & 0x7F
		value >>= 7
		if value:
			out.append(byte | 0x80)
		else:
			out.append(byte)
			return bytes(out)


def field_varint(number: int, value: int) -> bytes:
	return varint(number << 3) + varint(value)


def field_bytes(number: int, value: bytes) -> bytes:
	return varint((number << 3) | 2) + varint(len(value)) + value


def field_fixed64(number: int, value: float) -> bytes:
	return varint((number << 3) | 1) + struct.pack("<d", value)


def metric(name=None, alias=None, datatype=None, value=None, timestamp=None, is_null=False) -> bytes:
	out = b""
	if name is not None:
		out += field_bytes(1, name.encode())
	if alias is not None:
		out += field_varint(2, alias)
	if timestamp is not None:
		out += field_varint(3, timestamp)
	if datatype is not None:
		out += field_varint(4, datatype)
	if is_null:
		out += field_varint(7, 1)
	if value is not None:
		if datatype == DOUBLE:
			out += field_fixed64(13, value)
		elif datatype == BOOLEAN:
			out += field_varint(14, int(value))
		elif datatype == STRING:
			out += field_bytes(15, value.encode())
		elif datatype == UINT64:
			out += field_varint(11, value)
		else:
			out += field_varint(10, value & 0xFFFFFFFF)
	return field_bytes(2, out)


def payload(*metrics: bytes, timestamp=1_700_000_000_000, seq=0) -> bytes:
	return field_varint(1, timestamp) + b"".join(metrics) + field_varint(3, seq)


class TestDecoder(unittest.TestCase):
	def test_decodes_every_value_kind(self):
		data = payload(
			metric("Press1/good", alias=1, datatype=UINT64, value=1234, timestamp=1_700_000_001_000),
			metric("Press1/temp", datatype=DOUBLE, value=72.5),
			metric("Press1/offset", datatype=INT32, value=-3),
			metric("Press1/state", datatype=STRING, value="Running"),
			metric("Press1/ready", datatype=BOOLEAN, value=True),
			metric("Press1/empty", datatype=STRING, is_null=True),
			seq=7,
		)
		decoded = decode_payload(data)
		self.assertEqual((decoded.timestamp, decoded.seq), (1_700_000_000_000, 7))
		values = {m.name: m.value for m in decoded.metrics}
		self.assertEqual(values["Press1/good"], 1234)
		self.assertAlmostEqual(values["Press1/temp"], 72.5)
		self.assertEqual(values["Press1/offset"], -3)
		self.assertEqual(values["Press1/state"], "Running")
		self.assertIs(values["Press1/ready"], True)
		self.assertTrue(decoded.metrics[-1].is_null)
		self.assertEqual(decoded.metrics[0].alias, 1)
		self.assertEqual(decoded.metrics[0].timestamp, 1_700_000_001_000)

	def test_truncated_payload_is_rejected(self):
		with self.assertRaises(EventError):
			decode_payload(payload(metric("x", datatype=STRING, value="abc"))[:-4])


class TestTopics(unittest.TestCase):
	def test_topics(self):
		t = parse_sparkplug_topic("spBv1.0/Plant/DDATA/Edge1/Press1")
		self.assertEqual(t, Topic("Plant", "DDATA", "Edge1", "Press1"))
		self.assertEqual(t.machine_source_id, "Press1")
		n = parse_sparkplug_topic("spBv1.0/Plant/NDATA/Edge1")
		self.assertIsNone(n.device)
		self.assertEqual(n.machine_source_id, "Edge1")
		self.assertIsNone(parse_sparkplug_topic("spBv1.0/STATE/scada-host"))
		self.assertIsNone(parse_sparkplug_topic("foames/press/count"))


class TestEvents(unittest.TestCase):
	def test_convention_mapping_and_aliases(self):
		aliases = AliasBook()
		topic = Topic("Plant", "DBIRTH", "Edge1", "Press1")
		birth = decode_payload(
			payload(
				metric("Line/state", alias=1, datatype=STRING, value="run"),
				metric("Line/good", alias=2, datatype=UINT64, value=100),
				metric("Line/count/rework", alias=3, datatype=UINT64, value=4),
				metric("Line/temperature", alias=4, datatype=DOUBLE, value=70.0),
				metric("Line/label", alias=5, datatype=STRING, value="A"),
			)
		)
		events = message_to_raw_events(topic, birth, aliases)
		kinds = [(e["type"], e.get("counter") or e.get("name") or e.get("state")) for e in events]
		self.assertEqual(
			kinds,
			[("State", "run"), ("Count", "good"), ("Count", "rework"), ("Measurement", "Line/temperature")],
		)
		for e in events:
			self.assertEqual(e["machine"], "Press1")
			normalise_event(e, "MQTT")  # every event passes the common validation

		data = decode_payload(
			payload(metric(alias=2, datatype=UINT64, value=112, timestamp=1_700_000_005_000))
		)
		events = message_to_raw_events(Topic("Plant", "DDATA", "Edge1", "Press1"), data, aliases)
		self.assertEqual(len(events), 1)
		self.assertEqual((events[0]["counter"], events[0]["value"]), ("good", 112))
		self.assertEqual(events[0]["timestamp"], 1_700_000_005.0)
		self.assertEqual(normalise_event(events[0], "MQTT")["event_key"], events[0]["id"])

		# An alias that was never announced cannot be resolved and is skipped.
		data = decode_payload(payload(metric(alias=9, datatype=UINT64, value=1)))
		self.assertEqual(message_to_raw_events(Topic("Plant", "DDATA", "Edge1", "Press1"), data, aliases), [])

	def test_explicit_rows_win(self):
		class Row:
			source = "Sparkplug B"
			node_id = "Edge1/Press1/PLC/Status"
			machine = "PRESS-1"
			machine_source_id = "press-1"
			event_type = "State"
			name_or_counter = None
			state_map = "1=Running\n2=Down"

		data = decode_payload(payload(metric("PLC/Status", datatype=INT32, value=2)))
		events = message_to_raw_events(Topic("Plant", "DDATA", "Edge1", "Press1"), data, AliasBook(), [Row()])
		self.assertEqual(events[0]["machine"], "press-1")
		self.assertEqual(events[0]["state"], "Down")

	def test_death_marks_machines_unknown(self):
		aliases = AliasBook()
		aliases.learn(
			Topic("Plant", "DBIRTH", "Edge1", "Press1"), decode_payload(payload(metric("x", alias=1)))
		)
		aliases.learn(
			Topic("Plant", "DBIRTH", "Edge1", "Press2"), decode_payload(payload(metric("x", alias=1)))
		)
		events = message_to_raw_events(Topic("Plant", "NDEATH", "Edge1"), decode_payload(payload()), aliases)
		self.assertEqual(sorted(e["machine"] for e in events), ["Edge1", "Press1", "Press2"])
		self.assertTrue(all(e["state"] == "Unknown" for e in events))
		events = message_to_raw_events(
			Topic("Plant", "DDEATH", "Edge1", "Press1"), decode_payload(payload()), aliases
		)
		self.assertEqual([e["machine"] for e in events], ["Press1"])
