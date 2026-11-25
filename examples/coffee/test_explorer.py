# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Verify explorer records against source schemas and the replay's actual evidence."""

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from build import SCENARIO_IDS, STAGES, make_scenario
from explorer import build_explorer

from foames.foames_life_sciences.npi import STAGES as NPI_STAGES
from foames.foames_life_sciences.npi import decision_problems
from foames.foames_life_sciences.requirements import requirement_problems
from foames.foames_life_sciences.transfer import package_problems
from foames.foames_mes.work_instructions import validate_template_step

ROOT = Path(__file__).resolve().parents[2]


class CoffeeExplorerTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.scenarios = [make_scenario(k) for k in SCENARIO_IDS]
		cls.explorer = build_explorer(cls.scenarios)
		cls.schemas = {}
		for module in ("foames_mes", "foames_bms", "foames_life_sciences", "foames_validation"):
			for path in (ROOT / "foames" / module / "doctype").glob("*/*.json"):
				schema = json.loads(path.read_text(encoding="utf-8"))
				cls.schemas[schema["name"]] = schema

	def assert_single(self, rows):
		matches = list(rows)
		self.assertEqual(len(matches), 1, f"Expected exactly one matching sample, found {len(matches)}")
		return matches[0]

	def assert_document_matches_schema(self, document):
		schema = self.schemas[document["doctype"]]
		fields = {f["fieldname"]: f for f in schema["fields"]}
		self.assertLessEqual(set(document), set(fields) | {"doctype", "name"}, document)
		for field in fields.values():
			key = field["fieldname"]
			if field.get("reqd"):
				self.assertTrue(document.get(key), f"{document['doctype']}.{key} is required")
			if key not in document:
				continue
			if field["fieldtype"] == "Select":
				self.assertIn(document[key], (field.get("options") or "").splitlines())
			elif field["fieldtype"] == "Table":
				for row in document[key]:
					self.assertEqual(row["doctype"], field["options"])
					self.assert_document_matches_schema(row)

	def test_documents_and_children_match_actual_fields_and_enums(self):
		for sample in self.explorer["assets"] + self.explorer["work_instructions"]:
			with self.subTest(record=sample["id"]):
				self.assert_document_matches_schema(sample["document"])
				path = ROOT / sample["source_definition"]
				self.assertTrue(path.is_file())
				self.assertEqual(
					json.loads(path.read_text(encoding="utf-8"))["name"], sample["document"]["doctype"]
				)
		for key in ("program", "requirements", "transfer", "validation"):
			self.assert_document_matches_schema(self.explorer["npi"][key])
			self.assertTrue((ROOT / self.explorer["npi"]["source_definitions"][key]).is_file())

	def test_every_stage_has_typed_asset_and_consistent_instruction_links(self):
		assets = {a["id"]: a for a in self.explorer["assets"]}
		instructions = {i["id"]: i for i in self.explorer["work_instructions"]}
		self.assertEqual(set(STAGES), {s for a in assets.values() for s in a["stage_ids"]})
		self.assertEqual(assets["DEMO-ASSET-LAND"]["doctype"], "Facility Zone")
		self.assertEqual(assets["DEMO-ASSET-TRELLIS"]["doctype"], "Facility Asset")
		for kind in ("pulper", "dryer", "huller", "roaster", "packager", "grinder", "brewer", "espresso"):
			asset = self.assert_single(a for a in assets.values() if a["kind"] == kind)
			self.assertEqual(asset["doctype"], "Machine")
			self.assertEqual(asset["document"]["code"], asset["name"])
			self.assertEqual(asset["silhouette"], kind)
		for identity in ("DEMO-ASSET-HARVEST", "DEMO-ASSET-DELIVERY"):
			self.assertIn("Manual", assets[identity]["document"]["machine_type"])
		for asset in assets.values():
			for wi in asset["work_instruction_ids"]:
				self.assertIn(asset["id"], instructions[wi]["asset_ids"])
			if asset["doctype"] == "Facility Asset":
				self.assertEqual(assets[asset["document"]["zone"]]["doctype"], "Facility Zone")
		for instruction in instructions.values():
			for asset_id in instruction["asset_ids"]:
				self.assertTrue(set(instruction["stage_ids"]) & set(assets[asset_id]["stage_ids"]))
			if instruction["document"].get("machine"):
				self.assertEqual(assets[instruction["document"]["machine"]]["doctype"], "Machine")

	def test_hold_has_no_downstream_signals_or_capture_results(self):
		downstream = set(STAGES[7:])
		for asset in self.explorer["assets"]:
			if downstream & set(asset["stage_ids"]):
				for signal in asset["signals"]:
					self.assertEqual(signal["scenarios"]["moisture_hold"], [])
		for instruction in self.explorer["work_instructions"]:
			if downstream & set(instruction["stage_ids"]):
				self.assertIsNone(instruction["sample_evaluations"]["moisture_hold"])

	def test_packaging_charts_keep_baselines_null_gap_and_observed_deltas(self):
		packager = self.assert_single(a for a in self.explorer["assets"] if a["kind"] == "packager")
		self.assertEqual(packager["document"]["ideal_cycle_seconds"], 6)
		for scenario in self.scenarios:
			for counter in ("good", "scrap"):
				signal = self.assert_single(
					s for s in packager["signals"] if s["id"] == f"packager-{counter}-counter"
				)
				points = signal["scenarios"][scenario["id"]]
				if scenario["id"] == "moisture_hold":
					self.assertEqual(points, [])
					continue
				observed = [p["value"] for p in points if p["value"] is not None]
				self.assertEqual(observed, scenario["counter_readings"][counter])
				self.assertEqual(observed[-1] - observed[0], scenario["oee"][f"{counter}_count"])
				self.assertEqual(
					sum(p["value"] is None for p in points), int(scenario["id"] == "network_gap")
				)
				elapsed = datetime.fromisoformat(points[-1]["time"]) - datetime.fromisoformat(
					points[0]["time"]
				)
				self.assertEqual(elapsed.total_seconds() / 60, 90)
				self.assertEqual(signal["interpolation"], "none")
				self.assertEqual(signal["unit"], "bags")

	def test_other_charts_are_only_existing_observations_with_explicit_axes(self):
		for asset in self.explorer["assets"]:
			for signal in asset["signals"]:
				self.assertEqual(set(signal["scenarios"]), {s["id"] for s in self.scenarios})
				self.assertIn(signal["unit"], signal["y_axis"])
				if signal["kind"] == "categorical":
					continue
				self.assertIn("time", signal["x_axis"])
				if signal.get("origin") == "synthetic-pid-model":
					self.assertEqual(asset["id"], "DEMO-ASSET-ESPRESSO")
					continue
				if asset["kind"] == "packager":
					continue
				for scenario in self.scenarios:
					stage = scenario["stages"][asset["stage_ids"][0]]
					points = signal["scenarios"][scenario["id"]]
					self.assertLessEqual(
						len(points), 1, "Do not invent a thermal, growth or mass time profile"
					)
					for point in points:
						self.assertEqual(point["time"], stage["time"])
						metric = self.assert_single(
							m for m in stage["metrics"] if m["label"] == signal["label"]
						)
						self.assertEqual(point["value"], metric["value"])
						self.assertEqual(signal["unit"], metric["unit"])

	def test_categorical_stage_balances_reconcile_exact_scenario_streams(self):
		for asset in self.explorer["assets"]:
			stage = asset["stage_ids"][0]
			for signal in asset["signals"]:
				if signal["kind"] != "categorical":
					continue
				self.assertEqual(signal["label"], "Stage mass balance")
				self.assertIn("not individual machine telemetry", signal["source_note"])
				self.assertEqual(signal["interpolation"], "none")
				for scenario in self.scenarios:
					balances = [b for b in scenario["mass_balance"] if b["stage"] == stage]
					points = signal["scenarios"][scenario["id"]]
					inactive = (asset["kind"] == "espresso" and not scenario.get("espresso")) or (
						asset["kind"] == "brewer" and scenario.get("espresso")
					)
					if not balances or inactive:
						self.assertEqual(points, [])
						continue
					balance = self.assert_single(balances)
					self.assertEqual([p["time"] for p in points], ["Input", "Product", "Other"])
					self.assertEqual(
						[p["value"] for p in points],
						[balance["input_kg"], balance["output_kg"], balance["other_kg"]],
					)
					self.assertAlmostEqual(points[0]["value"], points[1]["value"] + points[2]["value"])
					self.assertEqual(signal["scenario_notes"][scenario["id"]], balance["other_label"])
		brewing = [a for a in self.explorer["assets"] if a["kind"] in ("grinder", "brewer")]
		self.assertEqual(len(brewing), 2)
		for asset in brewing:
			balance = self.assert_single(s for s in asset["signals"] if s["kind"] == "categorical")
			self.assertEqual(balance["scenarios"]["normal"][0]["value"], 0.354)

	def test_espresso_signals_are_scoped_to_the_model_and_filter_is_inactive(self):
		scenario = self.assert_single(s for s in self.scenarios if s["id"] == "espresso_pid")
		asset = self.assert_single(a for a in self.explorer["assets"] if a["kind"] == "espresso")
		self.assertEqual(asset["document"]["status"], "Unknown")
		self.assertEqual(asset["finish"]["body"], "#3683A4")
		self.assertEqual(asset["finish"]["accent"], "#A2A342")
		for signal in asset["signals"]:
			for kind in set(SCENARIO_IDS) - {"espresso_pid"}:
				self.assertEqual(signal["scenarios"][kind], [])
			if signal.get("origin") == "synthetic-pid-model":
				field = signal["id"].removeprefix("espresso-")
				self.assertEqual(
					signal["scenarios"]["espresso_pid"],
					[{"time": row["time"], "value": row[field]} for row in scenario["espresso"]["samples"]],
				)
		brewer = self.assert_single(a for a in self.explorer["assets"] if a["kind"] == "brewer")
		self.assertTrue(all(not s["scenarios"]["espresso_pid"] for s in brewer["signals"]))
		instruction = self.assert_single(
			w for w in self.explorer["work_instructions"] if w["id"] == "DEMO-WI-ESPRESSO"
		)
		self.assertEqual(instruction["sample_evaluations"]["espresso_pid"]["value_number"], 36)
		self.assertEqual(instruction["sample_evaluations"]["espresso_pid"]["record_id"], "DEMO-ESPRESSO-01")
		self.assertTrue(
			all(
				instruction["sample_evaluations"][kind] is None
				for kind in set(SCENARIO_IDS) - {"espresso_pid"}
			)
		)

	def test_work_instructions_are_drafts_and_moisture_evaluates_actual_rule(self):
		for instruction in self.explorer["work_instructions"]:
			self.assertEqual(instruction["status"], "Draft")
			self.assertNotIn("released_by", instruction["document"])
			for step in instruction["document"]["steps"]:
				self.assertEqual(validate_template_step(step), [])
				self.assertFalse(step.get("post_measurement"))
		drying = self.assert_single(
			w for w in self.explorer["work_instructions"] if w["stage_ids"] == ["drying"]
		)
		self.assertEqual(drying["sample_evaluations"]["normal"]["result"], "Pass")
		self.assertEqual(drying["sample_evaluations"]["moisture_hold"]["result"], "Fail")
		self.assertEqual(drying["sample_evaluations"]["moisture_hold"]["value_number"], 13.5)
		self.assertEqual(drying["document"]["steps"][1]["stop_on_fail"], 1)
		self.assertEqual(drying["document"]["steps"][1]["sign_off_role"], "FoaMES Quality")

	def test_npi_uses_shared_route_and_explicit_unfinished_coffee_deliverables(self):
		npi = self.explorer["npi"]
		program = npi["program"]
		self.assertEqual(npi["status"], "Proposed")
		self.assertEqual(program["product_type"], "Other")
		self.assertEqual(program["current_stage"], "Concept")
		self.assertEqual(tuple(g["stage"] for g in program["gates"]), NPI_STAGES)
		self.assertEqual(set(STAGES), {s for g in npi["gates"] for s in g["stage_ids"]})
		assets = {a["id"]: a for a in self.explorer["assets"]}
		for gate in npi["gates"]:
			for asset_id in gate["asset_ids"]:
				self.assertTrue(set(gate["stage_ids"]) & set(assets[asset_id]["stage_ids"]))
			self.assertEqual(gate["progress"]["percent_done"], 0)
		for row in program["gates"]:
			self.assertNotIn("decision", row)
		for row in program["deliverables"]:
			self.assertEqual(row["status"], "Not Started")
		for row in program["criteria"]:
			self.assertEqual(row["met"], 0)
			self.assertNotIn("evidence", row)
		self.assertTrue(
			decision_problems(
				program_status="Active",
				current_stage="Concept",
				gate_stage="Concept",
				decision="Go",
				deliverables=program["deliverables"],
			)
		)
		self.assertEqual(program["product_requirements"], npi["requirements"]["name"])
		self.assertEqual(program["tech_transfer_package"], npi["transfer"]["name"])
		self.assertEqual(requirement_problems(npi["requirements"]["requirements"]), [])
		self.assertEqual(npi["requirement_coverage"]["percent_verified"], 0)
		self.assertEqual(package_problems(npi["transfer"]["parameters"], npi["transfer"]["attributes"]), [])
		self.assertEqual(npi["validation"]["machine"], "DEMO-ASSET-DRYING")
		for key in ("requirements", "transfer", "validation"):
			self.assertNotIn("approved_by", npi[key])
			self.assertNotIn("approved_on", npi[key])

	def test_coverage_references_real_assets_instructions_and_guides(self):
		assets = {a["id"] for a in self.explorer["assets"]}
		instructions = {w["id"] for w in self.explorer["work_instructions"]}
		for row in self.explorer["coverage"]:
			self.assertLessEqual(set(row["asset_ids"]), assets)
			self.assertLessEqual(set(row["work_instruction_ids"]), instructions)
			self.assertLessEqual(set(row["stage_ids"]), set(STAGES))
			self.assertTrue((ROOT / row["guide_path"]).is_file(), row["guide_path"])
		self.assertTrue(any(r["status"] == "Guide only" for r in self.explorer["coverage"]))
		self.assertEqual(set(self.explorer["stage_views"]), set(STAGES))

	def test_builder_preserves_scenarios_and_returns_independent_serializable_data(self):
		before = copy.deepcopy(self.scenarios)
		built = build_explorer(self.scenarios)
		json.dumps(built, allow_nan=False)
		built["stage_views"]["land"]["supply"].append("Mutated copy")
		self.assertNotIn("Mutated copy", build_explorer(self.scenarios)["stage_views"]["land"]["supply"])
		self.assertEqual(before, self.scenarios)


if __name__ == "__main__":
	unittest.main()
