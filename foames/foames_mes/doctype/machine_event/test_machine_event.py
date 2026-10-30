# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe

from foames.foames_mes.api import record_events
from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine
from foames.tests_compat import IntegrationTestCase

HANDLED = []


def remember(event, machine):
	HANDLED.append((event.event_type, machine.name))


class TestMachineEvent(IntegrationTestCase):
	def setUp(self):
		self.machine = make_machine("T-PRESS", counter_rollover=10000)
		HANDLED.clear()

	def test_state_opens_and_closes_downtime(self):
		record_events(
			[
				{
					"machine": "T-PRESS",
					"type": "State",
					"state": "Running",
					"timestamp": "2026-10-20T08:00:00",
				},
				{"machine": "T-PRESS", "type": "State", "state": "fault", "timestamp": "2026-10-20T09:00:00"},
			]
		)
		self.assertEqual(frappe.db.get_value("Machine", "T-PRESS", "status"), "Down")
		open_dt = frappe.get_all("Downtime Record", {"machine": "T-PRESS", "status": "Open"})
		self.assertEqual(len(open_dt), 1)
		record_events(
			[{"machine": "T-PRESS", "type": "State", "state": "Running", "timestamp": "2026-10-20T09:30:00"}]
		)
		dt = frappe.get_doc("Downtime Record", open_dt[0].name)
		self.assertEqual((dt.status, dt.duration_minutes), ("Closed", 30))

	def test_counts_become_deltas_and_never_invent_production(self):
		result = record_events(
			[
				{
					"machine": "T-PRESS",
					"type": "Count",
					"value": 9990,
					"timestamp": "2026-10-20T08:00:00",
					"id": "a",
				},
				{
					"machine": "T-PRESS",
					"type": "Count",
					"value": 9995,
					"timestamp": "2026-10-20T08:01:00",
					"id": "b",
				},
				{
					"machine": "T-PRESS",
					"type": "Count",
					"value": 3,
					"timestamp": "2026-10-20T08:02:00",
					"id": "c",
				},
				{
					"machine": "T-PRESS",
					"type": "Count",
					"value": 3,
					"timestamp": "2026-10-20T08:02:00",
					"id": "c",
				},
			]
		)
		self.assertEqual(len(result["accepted"]), 3)
		self.assertEqual(result["rejected"][0]["reason"], "duplicate event id")
		deltas = frappe.get_all(
			"Machine Event",
			{"machine": "T-PRESS", "event_type": "Count"},
			["delta"],
			order_by="timestamp asc",
		)
		self.assertEqual([d.delta for d in deltas], [0, 5, 8])

	def test_late_reading_counts_zero(self):
		record_events(
			[
				{"machine": "T-PRESS", "type": "Count", "value": 100, "timestamp": "2026-10-20T08:00:00"},
				{"machine": "T-PRESS", "type": "Count", "value": 130, "timestamp": "2026-10-20T08:02:00"},
				{"machine": "T-PRESS", "type": "Count", "value": 110, "timestamp": "2026-10-20T08:01:00"},
			]
		)
		deltas = frappe.get_all(
			"Machine Event", {"machine": "T-PRESS", "event_type": "Count"}, ["delta"], order_by="creation asc"
		)
		self.assertEqual([d.delta for d in deltas], [0, 30, 0])

	def test_unknown_source_is_rejected_and_handlers_run(self):
		original = frappe.get_hooks

		def hooks(hook=None, *args, **kwargs):
			if hook == "foames_machine_event_handlers":
				return ["foames.foames_mes.doctype.machine_event.test_machine_event.remember"]
			return original(hook, *args, **kwargs)

		with patch.object(frappe, "get_hooks", side_effect=hooks):
			result = record_events(
				[
					{"machine": "no-such-machine", "type": "Message", "text": "hello"},
					{"machine": "T-PRESS", "type": "Message", "text": "hello"},
				]
			)
		self.assertEqual(len(result["rejected"]), 1)
		self.assertEqual(HANDLED, [("Message", "T-PRESS")])
