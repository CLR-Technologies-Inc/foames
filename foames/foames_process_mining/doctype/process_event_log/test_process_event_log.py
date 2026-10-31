# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe

from foames.foames_mes.api import record_events
from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine
from foames.foames_process_mining import api
from foames.foames_process_mining.discovery import discover_dfg
from foames.tests_compat import IntegrationTestCase


class TestProcessEventLog(IntegrationTestCase):
	def setUp(self):
		# A machine of its own per test, so records another test left behind cannot change the counts.
		self.machine = "T-PM-" + frappe.generate_hash(length=6).upper()
		make_machine(self.machine)
		m = self.machine
		record_events(
			[
				{"machine": m, "type": "State", "state": "Setup", "timestamp": "2026-10-21T08:00:00"},
				{"machine": m, "type": "State", "state": "Running", "timestamp": "2026-10-21T08:20:00"},
				{"machine": m, "type": "State", "state": "Down", "timestamp": "2026-10-21T10:00:00"},
				{"machine": m, "type": "State", "state": "Running", "timestamp": "2026-10-21T10:15:00"},
				{"machine": m, "type": "State", "state": "Idle", "timestamp": "2026-10-21T16:00:00"},
			]
		)

	def own(self, log):
		"""Only the events on this test's machine."""
		return log.filter(lambda e: self.machine in e.objects.get("machine", []))

	def make_log(self, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Process Event Log",
				"title": "Test log",
				"from_time": "2026-10-21 00:00:00",
				"to_time": "2026-10-22 00:00:00",
				**values,
			}
		).insert()
		doc.extract()
		return doc

	def test_extracts_machine_states_and_downtime(self):
		doc = self.make_log()
		self.assertEqual(doc.status, "Extracted")
		log = self.own(doc.load())
		case = f"{self.machine}:2026-10-21"
		self.assertEqual(log.case_ids(), [case, *[c for c in log.case_ids() if c != case]])
		states = [e.activity for e in log if e.case_id == case]
		self.assertEqual(states, ["Setup", "Running", "Down", "Running", "Idle"])
		# The Down state opened and closed a Downtime Record, which is its own trace.
		downtime = [e for e in log if "downtime" in e.objects]
		self.assertEqual([e.lifecycle for e in downtime], ["start", "complete"])
		self.assertEqual(log.summary()["cases"], 2)

	def test_discover_and_export(self):
		doc = self.make_log()
		result = doc.discover()
		edges = {(e["from"], e["to"]): e["count"] for e in result["dfg"]["edges"]}
		self.assertGreaterEqual(edges[("Running", "Down")], 1)
		self.assertGreaterEqual(edges[("Running", "Idle")], 1)
		self.assertIn("digraph", result["dot"])
		dfg = discover_dfg(self.own(doc.load()))
		self.assertEqual(dfg.edges[("Running", "Down")], 1)
		self.assertEqual(dfg.start_activities["Setup"], 1)
		url = doc.export_file("xes")
		self.assertTrue(url.endswith(".xes"))
		self.assertTrue(frappe.db.exists("File", {"attached_to_name": doc.name}))
		self.assertIn("eventTypes", api.export(event_log=doc.name, fmt="ocel"))

	def test_conformance_against_sequence_via_api(self):
		doc = self.make_log()
		report = api.check_conformance(model='["Setup", "Running", "Idle"]', event_log=doc.name)
		self.assertGreaterEqual(report["cases"], 2)  # at least this machine-day and its downtime record
		deviating = {t["case_id"] for t in report["traces"]}
		self.assertIn(f"{self.machine}:2026-10-21", deviating)  # Running -> Down is not in the sequence
		self.assertGreaterEqual(report["deviation_counts"].get("disallowed_transition", 0), 1)

	def test_api_builds_a_log_without_a_record(self):
		summary = api.summary(since="2026-10-21 00:00:00", until="2026-10-22 00:00:00")
		self.assertGreaterEqual(summary["events"], 5)
		result = api.discover(since="2026-10-21 00:00:00", until="2026-10-22 00:00:00", dot=1)
		self.assertIn("dot", result)

	def test_rejects_inverted_window(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Process Event Log",
					"title": "Bad",
					"from_time": "2026-10-22 00:00:00",
					"to_time": "2026-10-21 00:00:00",
				}
			).insert()
