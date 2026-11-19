# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0
"""Acceptance checks for the public replay, with independent expected arithmetic."""

import json
import tempfile
import unittest
from pathlib import Path

from build import (
	STAGES,
	build,
	build_data,
	coffee_ocel,
	descendants,
	event_log,
	make_scenario,
	validate_trace,
)

from foames.foames_process_mining.ocel import from_ocel, to_ocel


class CoffeeAcceptanceTests(unittest.TestCase):
	def test_delivered_cup_has_complete_origin_and_handoff(self):
		scenario = make_scenario()
		self.assertEqual(len(scenario["events"]), 12)
		self.assertEqual(tuple(scenario["stages"]), STAGES)
		self.assertEqual(scenario["cup"]["status"], "Delivered")
		self.assertEqual(scenario["cup"]["handoff_at"], scenario["events"][-1]["timestamp"])
		for origin in ("DEMO-SEED-01", "DEMO-PLOT-01", "DEMO-CHERRY-01", "DEMO-PACK-01"):
			self.assertIn("DEMO-CUP-01", descendants(scenario["trace"], origin))
		self.assertEqual(scenario["process_graph"]["cases"], 1)
		self.assertEqual(len(scenario["process_graph"]["edges"]), 11)

	def test_hold_does_not_invent_downstream_production_or_delivery(self):
		scenario = make_scenario("moisture_hold")
		self.assertIsNone(scenario["cup"]["handoff_at"])
		self.assertEqual(scenario["cup"]["beverage_g"], 0)
		self.assertEqual(scenario["oee"]["good_count"], 0)
		self.assertEqual(scenario["oee"]["ledger"]["planned_minutes"], 0)
		self.assertNotIn("DEMO-CUP-01", [n["id"] for n in scenario["trace"]])
		self.assertEqual(scenario["events"][-1]["activity"], "Hold parchment after moisture sample")
		for stage in STAGES[7:]:
			self.assertEqual(scenario["stages"][stage]["status"], "pending")
			self.assertEqual(scenario["stages"][stage]["metrics"], [])
			self.assertIsNone(scenario["stages"][stage]["time"])

	def test_packaging_oee_uses_baseline_deltas_and_exhaustive_time(self):
		for kind, good, run, unknown in (("normal", 550, 70, 0), ("network_gap", 450, 60, 10)):
			with self.subTest(kind=kind):
				scenario = make_scenario(kind)
				oee = scenario["oee"]
				self.assertEqual(oee["good_count"], good)
				self.assertEqual(oee["scrap_count"], 4)
				self.assertEqual(oee["ledger"]["run_minutes"], run)
				self.assertEqual(oee["ledger"]["unknown_minutes"], unknown)
				self.assertEqual(sum(v for k, v in oee["ledger"].items() if k != "planned_minutes"), 90)
				self.assertAlmostEqual(oee["availability"], run / 85)
				self.assertAlmostEqual(oee["quality"], good / (good + 4))
				self.assertAlmostEqual(oee["oee"], good * 6 / (85 * 60))
		self.assertLess(make_scenario("network_gap")["oee"]["oee"], make_scenario()["oee"]["oee"])

	def test_balances_and_brew_units(self):
		for kind in ("normal", "moisture_hold", "network_gap", "recall"):
			scenario = make_scenario(kind)
			for flow in scenario["mass_balance"]:
				self.assertAlmostEqual(flow["input_kg"], flow["output_kg"] + flow["other_kg"])
				self.assertGreaterEqual(flow["other_kg"], 0)
			if kind != "moisture_hold":
				pack = {row["stage"]: row for row in scenario["mass_balance"]}["packaging"]
				self.assertAlmostEqual(sum(pack["other_streams_kg"].values()), pack["other_kg"])
				self.assertAlmostEqual(
					pack["other_streams_kg"]["rejected_packages"], scenario["oee"]["scrap_count"] * 0.25
				)
				self.assertAlmostEqual(pack["output_kg"], scenario["oee"]["good_count"] * 0.25)
		cup = make_scenario()["cup"]
		self.assertAlmostEqual(cup["extraction_percent"], 20)
		self.assertEqual(cup["coffee_dose_g"], 18)
		self.assertEqual(cup["beverage_g"], 300)

	def test_recall_preserves_history_and_scopes_forward_trace(self):
		normal, recall = make_scenario(), make_scenario("recall")
		self.assertEqual(recall["cup"]["handoff_at"], normal["cup"]["handoff_at"])
		self.assertEqual(recall["events"][:12], normal["events"])
		self.assertEqual(
			recall["recall_affected_ids"], ["DEMO-BREW-01", "DEMO-CUP-01", "DEMO-PACK-01", "DEMO-SHIP-01"]
		)
		self.assertNotIn("DEMO-SEED-01", recall["recall_affected_ids"])
		self.assertEqual(recall["trace"][-1]["status"], "Delivered")

	def test_genealogy_rejects_missing_parent_duplicate_and_cycle(self):
		for nodes in (
			[{"id": "A", "parent_ids": ["missing"]}],
			[{"id": "A", "parent_ids": []}, {"id": "A", "parent_ids": []}],
			[{"id": "A", "parent_ids": ["B"]}, {"id": "B", "parent_ids": ["A"]}],
		):
			with self.assertRaises(ValueError):
				validate_trace(nodes)

	def test_ocel_keeps_event_identity_and_genealogy_objects(self):
		for kind in ("normal", "moisture_hold", "network_gap", "recall"):
			log = event_log(make_scenario(kind))
			exported = to_ocel(log)
			restored = from_ocel(exported)
			self.assertEqual([e.activity for e in log], [e.activity for e in restored])
			self.assertEqual([e.timestamp for e in log], [e.timestamp for e in restored])
			self.assertIn("DEMO-SEED-01", [o["id"] for o in exported["objects"]])

	def test_downloaded_ocel_preserves_complete_material_genealogy(self):
		for kind in ("normal", "network_gap", "recall"):
			exported = coffee_ocel(make_scenario(kind))
			objects = {o["id"]: o for o in exported["objects"]}
			pending, reached = ["DEMO-CUP-01"], set()
			while pending:
				identity = pending.pop()
				if identity not in reached:
					reached.add(identity)
					pending.extend(r["objectId"] for r in objects[identity].get("relationships", []))
			self.assertTrue({"DEMO-SEED-01", "DEMO-PLOT-01", "DEMO-PACK-01"} <= reached)
			self.assertEqual(len(reached), 14)

	def test_catalog_and_portable_build(self):
		data = build_data()
		self.assertEqual(len(data["stages"]), 12)
		self.assertEqual(len(data["scenarios"]), 4)
		with tempfile.TemporaryDirectory() as folder:
			build(folder)
			output = Path(folder)
			self.assertTrue((output / "index.html").is_file())
			self.assertEqual(json.loads((output / "data.json").read_text(encoding="utf-8")), data)
			self.assertEqual(len(list(output.glob("*.ocel.json"))), 4)


if __name__ == "__main__":
	unittest.main()
