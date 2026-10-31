# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The MQTT, OPC UA and Sparkplug B gateways against a site. The message handlers commit after each
event (they run in long-lived processes), so this module cleans up after itself explicitly."""

import frappe

from foames.foames_mes.gateway import mqtt, opcua, sparkplug
from foames.foames_mes.gateway.sparkplug import INT32, STRING, AliasBook
from foames.foames_mes.test_sparkplug import metric, payload
from foames.tests_compat import IntegrationTestCase

MACHINE = "T-GW"
SOURCE = "gw-press"


class GatewayTestCase(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.clean_rows()
		frappe.get_doc(
			{"doctype": "Machine", "code": MACHINE, "source_id": SOURCE, "counter_rollover": 0}
		).insert()
		frappe.db.commit()  # nosemgrep
		self.addCleanup(self.clean_up)

	def clean_up(self):
		frappe.db.rollback()
		self.clean_rows()
		frappe.db.commit()  # nosemgrep

	@staticmethod
	def clean_rows():
		frappe.db.delete("Machine Event", {"machine": MACHINE})
		frappe.db.delete("Downtime Record", {"machine": MACHINE})
		frappe.db.delete("Machine", {"name": MACHINE})

	def events(self):
		return frappe.get_all(
			"Machine Event",
			{"machine": MACHINE},
			["name", "event_type", "source", "counter_name", "counter_value", "state", "text"],
			order_by="creation asc",
		)


class TestMQTT(GatewayTestCase):
	def test_json_count_is_recorded(self):
		name = mqtt.handle_message(f"foames/{SOURCE}/Count", b'{"value": 5, "counter": "scrap"}', "foames")
		[event] = self.events()
		self.assertEqual(event.name, name)
		self.assertEqual(
			(event.event_type, event.source, event.counter_name, event.counter_value),
			("Count", "MQTT", "scrap", 5),
		)

	def test_bare_payload_is_the_value(self):
		mqtt.handle_message(f"foames/{SOURCE}/State", b"Running", "foames")
		[event] = self.events()
		self.assertEqual((event.event_type, event.state), ("State", "Running"))
		self.assertEqual(frappe.db.get_value("Machine", MACHINE, "status"), "Running")

	def test_bad_topic_and_unknown_machine_are_rejected(self):
		self.assertIsNone(mqtt.handle_message("other/x/Count", b"1", "foames"))
		self.assertIsNone(mqtt.handle_message("foames/no-such-machine/Count", b"1", "foames"))
		self.assertIsNone(mqtt.handle_message(f"foames/{SOURCE}/Count", b'{"value": "lots"}', "foames"))
		self.assertEqual(self.events(), [])

	def test_prefix_with_slashes_is_tolerated(self):
		self.assertTrue(mqtt.handle_message(f"plant/a/{SOURCE}/Message", b'{"text": "hello"}', "plant/a"))
		self.assertEqual(self.events()[0].text, "hello")


class TestOPCUA(GatewayTestCase):
	def row(self, **overrides):
		values = {
			"machine": MACHINE,
			"source": "OPC UA",
			"node_id": "ns=2;i=5",
			"event_type": "Count",
			"name_or_counter": None,
			"state_map": None,
		}
		values.update(overrides)
		return frappe._dict(values)

	def test_state_values_go_through_the_map(self):
		row = self.row(event_type="State", state_map="1=Running\n2=Down\n 3 = Idle ")
		self.assertEqual(
			opcua.node_value_to_raw(row, 1), {"machine": SOURCE, "type": "State", "state": "Running"}
		)
		self.assertEqual(opcua.node_value_to_raw(row, "3")["state"], "Idle")
		# An unmapped value passes through, so a server that already sends state names works.
		self.assertEqual(opcua.node_value_to_raw(row, "Setup")["state"], "Setup")

	def test_counts_default_to_the_good_counter(self):
		self.assertEqual(
			opcua.node_value_to_raw(self.row(), 42),
			{"machine": SOURCE, "type": "Count", "counter": "good", "value": 42},
		)
		self.assertEqual(opcua.node_value_to_raw(self.row(name_or_counter="scrap"), 1)["counter"], "scrap")

	def test_measurements_are_named_after_the_node_by_default(self):
		raw = opcua.node_value_to_raw(self.row(event_type="Measurement"), 71.5)
		self.assertEqual((raw["type"], raw["name"], raw["value"]), ("Measurement", "ns=2;i=5", 71.5))
		self.assertEqual(
			opcua.node_value_to_raw(self.row(event_type="Measurement", name_or_counter="temp"), 1)["name"],
			"temp",
		)

	def test_alarms_and_messages(self):
		self.assertEqual(opcua.node_value_to_raw(self.row(event_type="Alarm"), 7)["value"], 7)
		self.assertEqual(opcua.node_value_to_raw(self.row(event_type="Message"), 7)["text"], "7")

	def test_raw_events_record(self):
		from foames.foames_mes.api import record_event

		record_event(opcua.node_value_to_raw(self.row(), 42), source="OPC UA")
		[event] = self.events()
		self.assertEqual((event.source, event.counter_value), ("OPC UA", 42))


class TestSparkplug(GatewayTestCase):
	TOPIC = f"spBv1.0/G1/DDATA/edge-1/{SOURCE}"

	def test_data_message_records_by_convention(self):
		data = payload(
			metric("Line/good", datatype=INT32, value=7, timestamp=1_700_000_001_000),
			metric("Line/state", datatype=STRING, value="Running", timestamp=1_700_000_001_000),
		)
		names = sparkplug.handle_message(self.TOPIC, data, AliasBook())
		self.assertEqual(len(names), 2)
		events = self.events()
		self.assertEqual({e.event_type for e in events}, {"Count", "State"})
		self.assertEqual({e.source for e in events}, {"MQTT"})
		self.assertEqual(frappe.db.get_value("Machine", MACHINE, "status"), "Running")

	def test_repeated_message_is_not_recorded_twice(self):
		data = payload(metric("Line/good", datatype=INT32, value=7, timestamp=1_700_000_001_000))
		self.assertEqual(len(sparkplug.handle_message(self.TOPIC, data, AliasBook())), 1)
		self.assertEqual(sparkplug.handle_message(self.TOPIC, data, AliasBook()), [])
		self.assertEqual(len(self.events()), 1)

	def test_aliases_learned_from_birth_are_used_for_data(self):
		aliases = AliasBook()
		birth = payload(metric("Line/good", alias=3, datatype=INT32, value=1, timestamp=1_700_000_000_000))
		sparkplug.handle_message(self.TOPIC.replace("DDATA", "DBIRTH"), birth, aliases)
		data = payload(metric(alias=3, datatype=INT32, value=5, timestamp=1_700_000_002_000))
		self.assertEqual(len(sparkplug.handle_message(self.TOPIC, data, aliases)), 1)
		counts = [e.counter_value for e in self.events() if e.event_type == "Count"]
		self.assertEqual(counts, [1, 5])

	def test_death_marks_the_machine_unknown(self):
		sparkplug.handle_message(
			self.TOPIC,
			payload(metric("Line/state", datatype=STRING, value="Running", timestamp=1_700_000_001_000)),
			AliasBook(),
		)
		self.assertEqual(frappe.db.get_value("Machine", MACHINE, "status"), "Running")
		sparkplug.handle_message(
			self.TOPIC.replace("DDATA", "DDEATH"), payload(timestamp=1_700_000_002_000), AliasBook()
		)
		self.assertEqual(frappe.db.get_value("Machine", MACHINE, "status"), "Unknown")

	def test_other_topics_and_bad_payloads_are_ignored(self):
		self.assertEqual(sparkplug.handle_message("spBv1.0/G1/STATE/host", b"ONLINE", AliasBook()), [])
		self.assertEqual(sparkplug.handle_message(f"foames/{SOURCE}/Count", b"1", AliasBook()), [])
		self.assertEqual(sparkplug.handle_message(self.TOPIC, b"\xff\xff\xff", AliasBook()), [])
		self.assertEqual(self.events(), [])

	def test_unknown_device_records_nothing(self):
		data = payload(metric("Line/good", datatype=INT32, value=7, timestamp=1_700_000_001_000))
		self.assertEqual(sparkplug.handle_message("spBv1.0/G1/DDATA/edge-1/nobody", data, AliasBook()), [])
