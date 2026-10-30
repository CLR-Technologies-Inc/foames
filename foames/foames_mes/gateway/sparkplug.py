# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Sparkplug B gateway, the way Ignition SCADA publishes machine data.

Ignition's MQTT Transmission module (Cirrus Link) publishes tags as Sparkplug B messages on
`spBv1.0/<group>/<message type>/<edge node>[/<device>]`. The payload is a protobuf
`Payload` message with a list of metrics. This module decodes those payloads with no dependency
beyond the standard library (the Sparkplug B schema is small and public), resolves metric aliases
from BIRTH messages, and turns metrics into the same raw events the webhook and the plain MQTT
gateway produce. Run it as a long-lived process:

    bench --site <site> execute foames.foames_mes.gateway.sparkplug.run

Which machine a metric belongs to, and what it means, is decided in this order:

1. A Machine Data Settings map row with source Sparkplug B whose path matches
   `<group>/<edge node>/<device>/<metric name>` (or without the group, or without the device).
2. Convention: the device id (or the edge node id when there is no device) is the machine's
   source id, and the metric's last path segment names the event: `state`, `good`, `scrap`,
   `count/<name>`, `alarm`, `message`; anything else is a Measurement named after the metric.

NBIRTH and DBIRTH carry current values and are recorded like data; NDEATH and DDEATH set the
machines they cover to Unknown. Host STATE messages are ignored.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from foames.foames_mes.gateway.mapping import EventError, parse_state_map

NAMESPACE = "spBv1.0"
MESSAGE_TYPES = ("NBIRTH", "NDEATH", "DBIRTH", "DDEATH", "NDATA", "DDATA", "NCMD", "DCMD")

# Sparkplug B data type codes, from the public specification.
INT8, INT16, INT32, INT64 = 1, 2, 3, 4
UINT8, UINT16, UINT32, UINT64 = 5, 6, 7, 8
FLOAT, DOUBLE, BOOLEAN, STRING, DATETIME, TEXT, UUID = 9, 10, 11, 12, 13, 14, 15
SIGNED = {INT8: 8, INT16: 16, INT32: 32, INT64: 64}


# Protobuf wire format --------------------------------------------------------------------------


def _varint(data: bytes, pos: int) -> tuple[int, int]:
	result, shift = 0, 0
	while True:
		if pos >= len(data):
			raise EventError("truncated Sparkplug payload")
		byte = data[pos]
		pos += 1
		result |= (byte & 0x7F) << shift
		if not byte & 0x80:
			return result, pos
		shift += 7
		if shift > 70:
			raise EventError("bad varint in Sparkplug payload")


def _fields(data: bytes):
	"""Yield (field number, wire type, value) for a protobuf message. Values are ints for varints
	and fixed fields, bytes for length-delimited fields."""
	pos = 0
	while pos < len(data):
		key, pos = _varint(data, pos)
		number, wire = key >> 3, key & 7
		if wire == 0:
			value, pos = _varint(data, pos)
		elif wire == 1:
			value, pos = data[pos : pos + 8], pos + 8
		elif wire == 2:
			length, pos = _varint(data, pos)
			value, pos = data[pos : pos + length], pos + length
		elif wire == 5:
			value, pos = data[pos : pos + 4], pos + 4
		else:
			raise EventError(f"unsupported protobuf wire type {wire}")
		if pos > len(data):
			raise EventError("truncated Sparkplug payload")
		yield number, wire, value


def _signed(value: int, bits: int) -> int:
	value &= (1 << bits) - 1
	return value - (1 << bits) if value & (1 << (bits - 1)) else value


# Payload model ---------------------------------------------------------------------------------


@dataclass
class Metric:
	name: str | None = None
	alias: int | None = None
	timestamp: int | None = None  # milliseconds since the epoch
	datatype: int | None = None
	value: object = None
	is_null: bool = False
	is_historical: bool = False


@dataclass
class Payload:
	timestamp: int | None = None
	seq: int | None = None
	metrics: list[Metric] = field(default_factory=list)


def decode_metric(data: bytes) -> Metric:
	m = Metric()
	for number, _wire, value in _fields(data):
		if number == 1:
			m.name = value.decode("utf-8", errors="replace")
		elif number == 2:
			m.alias = value
		elif number == 3:
			m.timestamp = value
		elif number == 4:
			m.datatype = value
		elif number == 5:
			m.is_historical = bool(value)
		elif number == 7:
			m.is_null = bool(value)
		elif number == 10:  # int_value (uint32 on the wire)
			m.value = value
		elif number == 11:  # long_value (uint64 on the wire)
			m.value = value
		elif number == 12:  # float_value
			m.value = struct.unpack("<f", value)[0]
		elif number == 13:  # double_value
			m.value = struct.unpack("<d", value)[0]
		elif number == 14:  # boolean_value
			m.value = bool(value)
		elif number == 15:  # string_value
			m.value = value.decode("utf-8", errors="replace")
		elif number == 16:  # bytes_value
			m.value = bytes(value)
		# 8 metadata, 9 properties, 17 dataset, 18 template: not needed for machine events
	if m.datatype in SIGNED and isinstance(m.value, int) and not isinstance(m.value, bool):
		m.value = _signed(m.value, SIGNED[m.datatype])
	if m.datatype == DATETIME and isinstance(m.value, int):
		m.value = m.value / 1000.0  # milliseconds to seconds
	return m


def decode_payload(data: bytes) -> Payload:
	payload = Payload()
	for number, _wire, value in _fields(data):
		if number == 1:
			payload.timestamp = value
		elif number == 2:
			payload.metrics.append(decode_metric(value))
		elif number == 3:
			payload.seq = value
	return payload


# Topics ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Topic:
	group: str
	message_type: str
	edge_node: str
	device: str | None = None

	@property
	def machine_source_id(self) -> str:
		return self.device or self.edge_node


def parse_sparkplug_topic(topic: str) -> Topic | None:
	"""`spBv1.0/<group>/<type>/<edge node>[/<device>]`, or None for anything else (STATE included)."""
	parts = topic.split("/")
	if len(parts) < 4 or parts[0] != NAMESPACE or parts[2] not in MESSAGE_TYPES:
		return None
	device = "/".join(parts[4:]) or None
	return Topic(group=parts[1], message_type=parts[2], edge_node=parts[3], device=device)


# Aliases ---------------------------------------------------------------------------------------


class AliasBook:
	"""Metric names by alias, learned from BIRTH messages, per edge node and device."""

	def __init__(self):
		self._names: dict[tuple[str, str, str | None], dict[int, str]] = {}

	def learn(self, topic: Topic, payload: Payload):
		book = self._names.setdefault((topic.group, topic.edge_node, topic.device), {})
		for m in payload.metrics:
			if m.alias is not None and m.name:
				book[m.alias] = m.name

	def resolve(self, topic: Topic, metric: Metric) -> str | None:
		if metric.name:
			return metric.name
		if metric.alias is None:
			return None
		return self._names.get((topic.group, topic.edge_node, topic.device), {}).get(metric.alias)

	def devices_of(self, group: str, edge_node: str) -> list[str]:
		return [d for g, e, d in self._names if g == group and e == edge_node and d]


# Metrics to events -----------------------------------------------------------------------------

COUNTERS = {"good", "scrap", "count", "total", "parts", "reject", "bad", "ng"}


def match_row(rows, topic: Topic, metric_name: str):
	"""The map row whose path names this metric, with or without the group and device."""
	candidates = {
		f"{topic.group}/{topic.edge_node}/{topic.device}/{metric_name}" if topic.device else None,
		f"{topic.group}/{topic.edge_node}/{metric_name}",
		f"{topic.edge_node}/{topic.device}/{metric_name}" if topic.device else None,
		f"{topic.edge_node}/{metric_name}",
	}
	for row in rows or []:
		if getattr(row, "source", None) == "Sparkplug B" and row.node_id in candidates:
			return row
	return None


def metric_to_raw(topic: Topic, name: str, metric: Metric, payload: Payload, rows=None) -> dict | None:
	"""One raw event dict for `record_event`, or None when the metric carries nothing to record."""
	if metric.is_null or metric.value is None:
		return None
	timestamp_ms = metric.timestamp or payload.timestamp
	base = {
		"timestamp": timestamp_ms / 1000.0 if timestamp_ms else None,
		"id": f"sp:{topic.group}/{topic.edge_node}/{topic.device or ''}:{timestamp_ms}:{name}",
	}
	row = match_row(rows, topic, name)
	if row:
		base["machine"] = row.machine_source_id if hasattr(row, "machine_source_id") else row.machine
		base["type"] = row.event_type
		if row.event_type == "State":
			base["state"] = parse_state_map(row.state_map).get(str(metric.value), metric.value)
		elif row.event_type == "Count":
			base["counter"] = row.name_or_counter or "good"
			base["value"] = metric.value
		elif row.event_type == "Measurement":
			base["name"] = row.name_or_counter or name
			base["value"] = metric.value
		elif row.event_type == "Alarm":
			base["value"] = metric.value
		else:
			base["text"] = str(metric.value)
		return base

	base["machine"] = topic.machine_source_id
	last = name.rsplit("/", 1)[-1].strip().lower()
	if last == "state":
		base["type"] = "State"
		base["state"] = metric.value
	elif last in COUNTERS:
		base["type"] = "Count"
		base["counter"] = last
		base["value"] = metric.value
	elif "/" in name and name.rsplit("/", 2)[-2].lower() == "count":
		base["type"] = "Count"
		base["counter"] = last
		base["value"] = metric.value
	elif last == "alarm":
		base["type"] = "Alarm"
		base["value"] = metric.value if isinstance(metric.value, int | float) else 1
		base["text"] = str(metric.value)
	elif last == "message":
		base["type"] = "Message"
		base["text"] = str(metric.value)
	elif isinstance(metric.value, int | float) and not isinstance(metric.value, bool):
		base["type"] = "Measurement"
		base["name"] = name
		base["value"] = metric.value
	else:
		return None
	return base


def message_to_raw_events(topic: Topic, payload: Payload, aliases: AliasBook, rows=None) -> list[dict]:
	"""All raw events one Sparkplug message yields, after alias resolution."""
	if topic.message_type in ("NBIRTH", "DBIRTH"):
		aliases.learn(topic, payload)
	elif topic.message_type in ("NDEATH", "DDEATH"):
		machines = [topic.machine_source_id]
		if topic.message_type == "NDEATH":
			machines += aliases.devices_of(topic.group, topic.edge_node)
		ts = payload.timestamp / 1000.0 if payload.timestamp else None
		return [{"machine": m, "type": "State", "state": "Unknown", "timestamp": ts} for m in machines]
	elif topic.message_type in ("NCMD", "DCMD"):
		return []
	events = []
	for metric in payload.metrics:
		name = aliases.resolve(topic, metric)
		if not name:
			continue
		raw = metric_to_raw(topic, name, metric, payload, rows)
		if raw:
			events.append(raw)
	return events


# Gateway ---------------------------------------------------------------------------------------


def handle_message(topic_text: str, payload_bytes: bytes, aliases: AliasBook, rows=None) -> list[str]:
	"""Record every event in one Sparkplug message. Returns the Machine Event names."""
	import frappe

	from foames.foames_mes.api import record_event

	topic = parse_sparkplug_topic(topic_text)
	if not topic:
		return []
	names = []
	try:
		payload = decode_payload(payload_bytes)
	except EventError as e:
		frappe.logger("foames.sparkplug").warning(f"rejected {topic_text}: {e}")
		return names
	for raw in message_to_raw_events(topic, payload, aliases, rows):
		try:
			names.append(record_event(raw, source="MQTT"))
			frappe.db.commit()
		except EventError as e:
			frappe.logger("foames.sparkplug").warning(f"rejected {topic_text} {raw.get('type')}: {e}")
		except frappe.DuplicateEntryError:
			frappe.db.rollback()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="Sparkplug gateway", message=frappe.get_traceback())
	return names


def run():
	import frappe

	try:
		import paho.mqtt.client as mqtt
	except ImportError:
		raise SystemExit("The Sparkplug gateway needs paho-mqtt: pip install paho-mqtt")

	settings = frappe.get_single("Machine Data Settings")
	if not settings.sparkplug_enabled:
		raise SystemExit("Sparkplug B is not enabled in Machine Data Settings")
	group = (settings.sparkplug_group_id or "").strip() or "+"
	aliases = AliasBook()
	rows = [
		frappe._dict(
			source=r.source,
			node_id=r.node_id,
			machine=r.machine,
			machine_source_id=frappe.db.get_value("Machine", r.machine, "source_id") or r.machine,
			event_type=r.event_type,
			name_or_counter=r.name_or_counter,
			state_map=r.state_map,
		)
		for r in settings.node_map
		if r.source == "Sparkplug B"
	]

	client = mqtt.Client()
	if settings.mqtt_username:
		client.username_pw_set(
			settings.mqtt_username, settings.get_password("mqtt_password", raise_exception=False)
		)
	if settings.mqtt_tls:
		client.tls_set()

	def on_connect(c, userdata, flags, rc, *args):
		c.subscribe(f"{NAMESPACE}/{group}/#")

	def on_message(c, userdata, message):
		handle_message(message.topic, message.payload, aliases, rows)

	client.on_connect = on_connect
	client.on_message = on_message
	client.connect(settings.mqtt_broker, settings.mqtt_port or 1883, keepalive=60)
	client.loop_forever()
