# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json

import frappe

from foames.foames_mes.api import record_events
from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine
from foames.foames_process_mining.extractors import build_event_log
from foames.tests_compat import IntegrationTestCase


class TestEventLogSource(IntegrationTestCase):
	def setUp(self):
		# A machine of its own per test, so records another test left behind cannot change the counts.
		self.machine = "T-ELS-" + frappe.generate_hash(length=6).upper()
		make_machine(self.machine)
		m = self.machine
		record_events(
			[
				{"machine": m, "type": "Count", "value": 0, "timestamp": "2026-10-22T08:00:00"},
				{"machine": m, "type": "Count", "value": 50, "timestamp": "2026-10-22T09:00:00"},
				{
					"machine": m,
					"type": "Count",
					"counter": "scrap",
					"value": 2,
					"timestamp": "2026-10-22T09:00:00",
				},
			]
		)

	def test_field_mapped_source_over_a_foames_doctype(self):
		# Mine Machine Event itself: one trace per machine, one activity per counter reading.
		source = frappe.get_doc(
			{
				"doctype": "Event Log Source",
				"source_name": "T Counts " + self.machine,
				"source_doctype": "Machine Event",
				"case_field": "machine",
				"activity_field": "counter_name",
				"timestamp_field": "timestamp",
				"resource_field": "source",
				"filters": json.dumps({"event_type": "Count", "machine": self.machine}),
				"attribute_fields": "delta",
				"object_fields": "machine",
			}
		).insert()
		events = source.extract("2026-10-22 00:00:00", "2026-10-23 00:00:00")
		self.assertEqual([e.activity for e in events], ["good", "good", "scrap"])
		self.assertEqual(events[0].objects, {"machine": [self.machine]})
		self.assertEqual(events[0].attributes["source_doctype"], "Machine Event")
		log = build_event_log(
			"2026-10-22 00:00:00", "2026-10-23 00:00:00", sources=[source.name], built_in=False
		)
		self.assertEqual(log.summary()["cases"], 1)
		preview = source.preview(limit=2)
		self.assertTrue(preview["installed"])
		self.assertEqual(len(preview["events"]), 2)

	def test_missing_doctype_is_skipped_not_fatal(self):
		source = frappe.get_doc(
			{
				"doctype": "Event Log Source",
				"source_name": "T Absent " + self.machine,
				"source_doctype": "Not Installed Here",
				"case_field": "a",
				"fixed_activity": "x",
				"timestamp_field": "b",
			}
		).insert()
		self.assertEqual(source.extract(), [])
		self.assertFalse(source.preview()["installed"])

	def test_unknown_field_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Event Log Source",
					"source_name": "T Bad " + self.machine,
					"source_doctype": "Machine Event",
					"case_field": "machine",
					"fixed_activity": "x",
					"timestamp_field": "no_such_field",
				}
			).insert()

	def test_needs_an_activity(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Event Log Source",
					"source_name": "T No Activity " + self.machine,
					"source_doctype": "Machine Event",
					"case_field": "machine",
					"timestamp_field": "timestamp",
				}
			).insert()
