# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The floor snapshot, the pieces it is built from and the rules run over it, on a Frappe site."""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from foames.foames_mes.api import get_floor_snapshot, record_events, run_suggestion_rules
from foames.foames_mes.floor import collect_findings, counts_since, downtime_by_reason, floor_snapshot
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, extra_hooks, make_machine, make_reason, make_user

EXTENDED = []


def extend_snapshot(snapshot, since, now):
	EXTENDED.append((since, now))
	snapshot["extension"] = {"machines": len(snapshot["machines"])}


def extra_rule(snapshot):
	return [
		{
			"rule_key": "test-rule:fixed",
			"category": "Other",
			"severity": "Info",
			"title": "Test rule fired",
			"suggestion": "From a registered rule.",
			"evidence": {},
		}
	]


class TestDowntimeByReason(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-FL-DT")
		make_reason("T-FL-JAM", "Breakdown")
		make_reason("T-FL-PM", "Planned")
		self.since = get_datetime("2026-10-20 08:00:00")
		self.until = get_datetime("2026-10-20 16:00:00")

	def downtime(self, start, end, reason="T-FL-JAM", machine="T-FL-DT"):
		return frappe.get_doc(
			{
				"doctype": "Downtime Record",
				"machine": machine,
				"start_time": start,
				"end_time": end,
				"reason": reason,
			}
		).insert()

	def test_records_are_clipped_to_the_window(self):
		self.downtime("2026-10-20 07:00:00", "2026-10-20 09:00:00")  # 60 inside
		self.downtime("2026-10-20 10:00:00", "2026-10-20 10:30:00")  # 30 inside
		self.downtime("2026-10-20 15:30:00", "2026-10-20 17:00:00", "T-FL-PM")  # 30 inside
		self.downtime("2026-10-20 06:00:00", "2026-10-20 07:30:00")  # outside
		self.downtime("2026-10-20 16:00:00", "2026-10-20 17:00:00")  # starts at the end: outside
		self.assertEqual(
			downtime_by_reason("T-FL-DT", self.since, self.until), {"T-FL-JAM": 90, "T-FL-PM": 30}
		)

	def test_open_downtime_counts_up_to_until(self):
		self.downtime("2026-10-20 15:00:00", None)
		self.assertEqual(downtime_by_reason("T-FL-DT", self.since, self.until), {"T-FL-JAM": 60})

	def test_downtime_without_a_reason_is_not_attributed(self):
		self.downtime("2026-10-20 09:00:00", "2026-10-20 10:00:00", reason=None)
		self.assertEqual(downtime_by_reason("T-FL-DT", self.since, self.until), {})

	def test_other_machines_are_ignored(self):
		make_machine("T-FL-DT-2")
		self.downtime("2026-10-20 09:00:00", "2026-10-20 10:00:00", machine="T-FL-DT-2")
		self.assertEqual(downtime_by_reason("T-FL-DT", self.since, self.until), {})


class TestCountsSince(IntegrationTestCase):
	def test_deltas_are_summed_per_counter(self):
		make_machine("T-FL-CNT")
		record_events(
			[
				{"machine": "T-FL-CNT", "type": "Count", "value": 100, "timestamp": "2026-10-20 08:00:00"},
				{"machine": "T-FL-CNT", "type": "Count", "value": 130, "timestamp": "2026-10-20 09:00:00"},
				{"machine": "T-FL-CNT", "type": "Count", "value": 150, "timestamp": "2026-10-20 10:00:00"},
				{
					"machine": "T-FL-CNT",
					"type": "Count",
					"counter": "scrap",
					"value": 5,
					"timestamp": "2026-10-20 08:00:00",
				},
				{
					"machine": "T-FL-CNT",
					"type": "Count",
					"counter": "scrap",
					"value": 7,
					"timestamp": "2026-10-20 10:00:00",
				},
			]
		)
		self.assertEqual(
			counts_since("T-FL-CNT", get_datetime("2026-10-20 07:00:00")), {"good": 50, "scrap": 2}
		)
		# From 09:00 the first good reading at 08:00 is outside; its delta (0) is not missed.
		self.assertEqual(
			counts_since("T-FL-CNT", get_datetime("2026-10-20 09:00:00")), {"good": 50, "scrap": 2}
		)
		self.assertEqual(
			counts_since("T-FL-CNT", get_datetime("2026-10-20 09:30:00")), {"good": 20, "scrap": 2}
		)
		self.assertEqual(counts_since("T-FL-CNT", get_datetime("2026-10-21 00:00:00")), {})


class TestFloorSnapshot(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		EXTENDED.clear()
		self.now = now_datetime()
		make_machine("T-FL-A", title="Line A", ideal_cycle_seconds=30)
		make_machine("T-FL-B")
		make_machine("T-FL-OFF", disabled=1)
		make_reason("T-FL-JAM", "Breakdown")

	def ago(self, minutes):
		return add_to_date(self.now, minutes=-minutes)

	def test_machines_counts_and_downtime(self):
		record_events(
			[
				{"machine": "T-FL-A", "type": "State", "state": "Running", "timestamp": self.ago(120)},
				{"machine": "T-FL-A", "type": "Count", "value": 1000, "timestamp": self.ago(120)},
				{"machine": "T-FL-A", "type": "Count", "value": 1040, "timestamp": self.ago(45)},
				{"machine": "T-FL-A", "type": "State", "state": "Down", "timestamp": self.ago(40)},
				{"machine": "T-FL-A", "type": "State", "state": "Running", "timestamp": self.ago(10)},
			]
		)
		closed = frappe.db.get_value("Downtime Record", {"machine": "T-FL-A", "status": "Closed"}, "name")
		frappe.db.set_value("Downtime Record", closed, "reason", "T-FL-JAM")

		snapshot = floor_snapshot(days=1)
		names = [m.name for m in snapshot["machines"]]
		self.assertIn("T-FL-A", names)
		self.assertIn("T-FL-B", names)
		self.assertNotIn("T-FL-OFF", names)
		a = next(m for m in snapshot["machines"] if m.name == "T-FL-A")
		self.assertEqual((a.title, a.status, a.ideal_cycle_seconds), ("Line A", "Running", 30))
		self.assertEqual(a["counts"], {"good": 40})
		self.assertAlmostEqual(a["minutes_since_count"], 45, delta=1)
		self.assertIsNone(a["oee_today"])
		b = next(m for m in snapshot["machines"] if m.name == "T-FL-B")
		self.assertIsNone(b["minutes_since_count"])
		self.assertEqual(b["counts"], {})

		downtime = next(d for d in snapshot["downtime_by_machine"] if d["machine"] == "T-FL-A")
		self.assertEqual(downtime["top_reason"], "T-FL-JAM")
		self.assertAlmostEqual(downtime["top_minutes"], 30, delta=0.1)
		self.assertNotIn("T-FL-B", [d["machine"] for d in snapshot["downtime_by_machine"]])
		self.assertIsInstance(snapshot["open_suggestions"], list)
		self.assertIsInstance(snapshot["external_references"], list)
		self.assertTrue(snapshot["as_of"])

	def test_latest_oee_period_is_attached(self):
		for day in ("2026-10-18", "2026-10-19"):
			frappe.get_doc(
				{
					"doctype": "OEE Period",
					"machine": "T-FL-A",
					"from_time": f"{day} 06:00:00",
					"to_time": f"{day} 14:00:00",
					"planned_minutes": 480,
				}
			).insert()
		snapshot = floor_snapshot()
		a = next(m for m in snapshot["machines"] if m.name == "T-FL-A")
		self.assertEqual(set(a["oee_today"].keys()), {"oee", "availability", "performance", "quality"})
		latest = frappe.db.get_value(
			"OEE Period", {"machine": "T-FL-A", "from_time": "2026-10-19 06:00:00"}, "oee"
		)
		self.assertEqual(a["oee_today"]["oee"], latest)

	def test_window_in_days(self):
		record_events(
			[
				{
					"machine": "T-FL-A",
					"type": "Count",
					"value": 10,
					"timestamp": add_to_date(self.now, days=-3),
				},
				{
					"machine": "T-FL-A",
					"type": "Count",
					"value": 20,
					"timestamp": add_to_date(self.now, days=-2),
				},
				{"machine": "T-FL-A", "type": "Count", "value": 25, "timestamp": self.ago(30)},
			]
		)
		a = next(m for m in floor_snapshot(days=1)["machines"] if m.name == "T-FL-A")
		self.assertEqual(a["counts"], {"good": 5})
		a = next(m for m in floor_snapshot(days=5)["machines"] if m.name == "T-FL-A")
		self.assertEqual(a["counts"], {"good": 15})

	def test_missing_references_are_listed(self):
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		reference = frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "ERPNext",
				"reference_type": "Item",
				"external_id": "T-FL-MISSING",
			}
		).insert()
		frappe.db.set_value("External Reference", reference.name, "status", "Missing")
		missing = [r.name for r in floor_snapshot()["external_references"]]
		self.assertIn(reference.name, missing)
		self.assertTrue(all(r.status == "Missing" for r in floor_snapshot()["external_references"]))

	def test_extensions_and_registered_rules(self):
		with extra_hooks(
			foames_floor_snapshot_extensions=["foames.foames_mes.test_floor.extend_snapshot"],
			foames_suggestion_rules=["foames.foames_mes.test_floor.extra_rule"],
		):
			snapshot = floor_snapshot(days=2)
			self.assertEqual(snapshot["extension"]["machines"], len(snapshot["machines"]))
			since, now = EXTENDED[-1]
			self.assertAlmostEqual((now - since).total_seconds() / 3600, 48, delta=0.1)
			findings = collect_findings(snapshot)
			self.assertIn("test-rule:fixed", [f["rule_key"] for f in findings])

	def test_api_requires_machine_read_permission(self):
		make_user("foames-floor-nobody@example.com")
		make_user("foames-floor-quality@example.com", "FoaMES Quality")
		with as_user("foames-floor-nobody@example.com"), self.assertRaises(frappe.PermissionError):
			get_floor_snapshot()
		with as_user("foames-floor-quality@example.com"):
			snapshot = get_floor_snapshot(days="1")
			self.assertIn("T-FL-A", [m.name for m in snapshot["machines"]])
			# Quality cannot read External References, so that section is simply empty for them.
			self.assertEqual(snapshot["external_references"], [])


class TestRulesOnTheFloor(IntegrationTestCase):
	def test_silent_machine_raises_one_suggestion(self):
		make_machine("T-FL-SILENT")
		record_events(
			[
				{
					"machine": "T-FL-SILENT",
					"type": "Count",
					"value": 5,
					"timestamp": add_to_date(now_datetime(), minutes=-50),
				},
			]
		)
		frappe.get_doc("Machine", "T-FL-SILENT").db_set("status", "Unknown", update_modified=False)
		created = run_suggestion_rules()
		mine = frappe.get_all(
			"Agent Suggestion",
			{"reference_doctype": "Machine", "reference_name": "T-FL-SILENT", "status": "Open"},
			["name", "category", "rule_key", "agent"],
		)
		self.assertEqual(len(mine), 1)
		self.assertIn(mine[0].name, created)
		self.assertEqual((mine[0].category, mine[0].agent), ("Machine Data", "foames-rules"))
		self.assertTrue(mine[0].rule_key.startswith("silent:T-FL-SILENT:"))
		# Running the rules again does not raise the same finding twice.
		run_suggestion_rules()
		self.assertEqual(
			frappe.db.count("Agent Suggestion", {"reference_name": "T-FL-SILENT", "status": "Open"}), 1
		)

	def test_api_requires_create_permission(self):
		make_user("foames-floor-quality2@example.com", "FoaMES Quality")
		with as_user("foames-floor-quality2@example.com"), self.assertRaises(frappe.PermissionError):
			run_suggestion_rules()
