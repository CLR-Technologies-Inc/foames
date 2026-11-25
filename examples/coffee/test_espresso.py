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

"""Verify the espresso's material trace and causal, explicitly synthetic PID model."""

import copy
import hashlib
import json
import math
import tempfile
import unittest
from datetime import datetime
from itertools import pairwise
from pathlib import Path

from build import SCENARIO_IDS, STAGES, build, coffee_ocel, descendants, make_scenario, validate_trace
from espresso import PIDController, make_espresso_scenario, simulate_espresso

END_TIME = "2026-11-18T09:02:00-10:00"
# Captured before adding espresso: the original four full scenario payloads must not change.
ORIGINAL_SCENARIO_HASHES = {
	"normal": "507a2fa3b0bdae9449c3e15fcbead9d31bf401d2150e164f5d6c701ef266be99",
	"moisture_hold": "24c00687b3a750b4b88ea0c92826a5f906f0a36e860ac0bf2ab430040dee4deb",
	"network_gap": "0c6d4451cd5b2c95db3532f2c8d86b29cf597472e080307c070359577900b1c8",
	"recall": "9e4d0dfb67be6c1e4203a6d299fb977ce2e5202f18c021be7766090759a55b1b",
}


class EspressoThermalModelTests(unittest.TestCase):
	def test_replay_is_deterministic_finite_bounded_and_timed(self):
		model = simulate_espresso(END_TIME)
		self.assertEqual(model, simulate_espresso(END_TIME))
		self.assertEqual(model["asset_id"], "DEMO-ASSET-ESPRESSO")
		self.assertIn("not measured Gaggia dynamics", model["model_note"])
		self.assertEqual(model["duration_seconds"], 90)
		samples = model["samples"]
		self.assertEqual([s["elapsed_s"] for s in samples], list(range(91)))
		self.assertEqual(samples[-1]["time"], END_TIME)
		self.assertEqual(samples[0]["temperature_c"], 90)
		for sample in samples:
			for key in ("temperature_c", "setpoint_c", "heater_percent", "beverage_g"):
				self.assertTrue(math.isfinite(sample[key]))
			self.assertTrue(0 <= sample["heater_percent"] <= 100)
			self.assertTrue(80 <= sample["temperature_c"] <= 100)
			self.assertTrue(0 <= sample["beverage_g"] <= 36)
			self.assertEqual(sample["setpoint_c"], 93)
		for before, after in pairwise(samples):
			delta = datetime.fromisoformat(after["time"]) - datetime.fromisoformat(before["time"])
			self.assertEqual(delta.total_seconds(), 1)
			self.assertGreaterEqual(after["beverage_g"], before["beverage_g"])
		self.assertEqual(samples[44]["phase"], "Warming")
		self.assertEqual(samples[45]["phase"], "Brewing")
		self.assertEqual(samples[74]["phase"], "Brewing")
		self.assertEqual(samples[75]["phase"], "Recovering")
		self.assertEqual(samples[45]["beverage_g"], 0)
		self.assertEqual(samples[75]["beverage_g"], 36)
		self.assertTrue(all(s["beverage_g"] == 36 for s in samples[75:]))

	def test_brew_load_causes_temperature_drop_and_controller_response(self):
		loaded = simulate_espresso(END_TIME)["samples"]
		unloaded = simulate_espresso(END_TIME, brew_load_c_per_s=0)["samples"]
		self.assertEqual(loaded[:46], unloaded[:46])
		self.assertLess(loaded[46]["temperature_c"], unloaded[46]["temperature_c"])
		self.assertGreater(loaded[46]["heater_percent"], unloaded[46]["heater_percent"])
		self.assertGreater(loaded[60]["heater_percent"], unloaded[60]["heater_percent"])
		self.assertGreater(loaded[76]["temperature_c"], loaded[75]["temperature_c"])
		self.assertLess(loaded[76]["heater_percent"], loaded[75]["heater_percent"])
		# Cup fill is an explicit scenario assumption, not a thermal-model production prediction.
		self.assertEqual([s["beverage_g"] for s in loaded], [s["beverage_g"] for s in unloaded])
		unheated = simulate_espresso(END_TIME, heater_rise_c_per_s=0)["samples"]
		self.assertLess(unheated[44]["temperature_c"], unheated[0]["temperature_c"])
		self.assertGreater(loaded[44]["temperature_c"], loaded[0]["temperature_c"])

	def test_proportional_integral_and_derivative_terms_have_distinct_effects(self):
		proportional = PIDController(kp=0.2, ki=0, kd=0)
		self.assertAlmostEqual(proportional.step(92, 93), 0.2)
		self.assertAlmostEqual(proportional.step(91, 93), 0.4)
		integrating = PIDController(kp=0, ki=0.1, kd=0)
		self.assertAlmostEqual(integrating.step(92, 93), 0.1)
		self.assertAlmostEqual(integrating.step(92, 93), 0.2)
		derivative = PIDController(kp=0, ki=0, kd=0.2, integral=0.5)
		self.assertAlmostEqual(derivative.step(93, 93), 0.5)
		self.assertAlmostEqual(derivative.step(94, 93), 0.3)
		self.assertAlmostEqual(derivative.step(92, 93), 0.9)

	def test_saturation_does_not_wind_up_integral(self):
		controller = PIDController(kp=1, ki=0.5, kd=0)
		for _ in range(100):
			self.assertEqual(controller.step(90, 93), 1)
		self.assertEqual(controller.integral, 0)
		self.assertEqual(controller.step(93, 93), 0)
		self.assertEqual(controller.step(100, 93), 0)
		self.assertTrue(0 <= controller.integral <= 1)

	def test_invalid_model_inputs_fail_explicitly(self):
		for invalid in (float("nan"), float("inf"), -0.1):
			with self.subTest(coefficient=invalid), self.assertRaises(ValueError):
				simulate_espresso(END_TIME, brew_load_c_per_s=invalid)
		for invalid in (0, -1, float("nan")):
			with self.subTest(dt=invalid), self.assertRaises(ValueError):
				PIDController().step(90, 93, dt=invalid)
		with self.assertRaisesRegex(ValueError, "timezone-aware"):
			simulate_espresso("2026-11-18T09:02:00")


class EspressoScenarioTests(unittest.TestCase):
	def test_espresso_balances_and_extraction_are_consistent(self):
		scenario = make_scenario("espresso_pid")
		cup, model = scenario["cup"], scenario["espresso"]
		self.assertEqual((cup["coffee_dose_g"], cup["beverage_g"], cup["tds_percent"]), (18, 36, 10))
		self.assertAlmostEqual(cup["extraction_percent"], 36 * 0.10 / 18 * 100)
		self.assertEqual(cup["extraction_percent"], 20)
		self.assertEqual((model["dose_g"], model["yield_g"], model["water_g"]), (18, 36, 54))
		balances = {b["stage"]: b for b in scenario["mass_balance"]}
		self.assertEqual(balances["brewing"]["input_kg"], 0.072)
		self.assertEqual(balances["brewing"]["output_kg"], 0.036)
		self.assertEqual(balances["brewing"]["other_kg"], 0.036)
		for balance in balances.values():
			self.assertAlmostEqual(balance["input_kg"], balance["output_kg"] + balance["other_kg"])
		self.assertIn("leaving 232 g", scenario["stages"]["brewing"]["note"])
		self.assertEqual(model["samples"][-1]["time"], scenario["stages"]["brewing"]["time"])
		self.assertEqual(cup["handoff_at"], scenario["events"][-1]["timestamp"])
		self.assertGreater(cup["handoff_at"], model["samples"][-1]["time"])

	def test_espresso_genealogy_and_ocel_record_an_explicit_handoff(self):
		scenario = make_scenario("espresso_pid")
		validate_trace(scenario["trace"])
		trace = {r["id"]: r for r in scenario["trace"]}
		self.assertNotIn("DEMO-BREW-01", trace)
		self.assertNotIn("DEMO-CUP-01", trace)
		self.assertEqual(trace["DEMO-ESPRESSO-01"]["parent_ids"], ["DEMO-SHIP-01", "DEMO-ORDER-01"])
		self.assertEqual(trace["DEMO-ESPRESSO-CUP-01"]["parent_ids"], ["DEMO-ESPRESSO-01", "DEMO-ORDER-01"])
		for source in ("DEMO-SEED-01", "DEMO-PLOT-01", "DEMO-PACK-01"):
			self.assertIn("DEMO-ESPRESSO-CUP-01", descendants(scenario["trace"], source))
		exported = coffee_ocel(scenario)
		objects = {o["id"]: o for o in exported["objects"] if o["type"] == "record"}
		self.assertEqual(set(objects), set(trace))
		for identity in ("DEMO-ESPRESSO-01", "DEMO-ESPRESSO-CUP-01"):
			self.assertIn(
				{"objectId": "DEMO-ORDER-01", "qualifier": "fulfillsOrder"},
				objects[identity]["relationships"],
			)
		self.assertIn(
			{"objectId": "DEMO-ESPRESSO-01", "qualifier": "derivedFrom"},
			objects["DEMO-ESPRESSO-CUP-01"]["relationships"],
		)
		events = {e["type"]: e for e in exported["events"]}
		self.assertIn("Confirm espresso cup handoff", events)
		self.assertNotIn("Complete filter brew", events)
		self.assertEqual(
			{
				r["objectId"]
				for r in events["Confirm espresso cup handoff"]["relationships"]
				if r["objectId"] in objects
			},
			{"DEMO-ESPRESSO-CUP-01", "DEMO-ESPRESSO-01", "DEMO-ORDER-01"},
		)
		self.assertEqual(scenario["process_graph"]["cases"], 1)
		self.assertEqual(len(scenario["process_graph"]["edges"]), 11)
		self.assertEqual(len(scenario["events"]), 12, "Thermal samples do not invent business events")

	def test_original_scenarios_and_espresso_upstream_are_unchanged(self):
		for kind, digest in ORIGINAL_SCENARIO_HASHES.items():
			with self.subTest(scenario=kind):
				payload = json.dumps(make_scenario(kind), sort_keys=True, separators=(",", ":")).encode()
				self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)
		normal = make_scenario("normal")
		before = copy.deepcopy(normal)
		espresso = make_espresso_scenario(normal)
		self.assertEqual(normal, before)
		for stage in STAGES[:10]:
			self.assertEqual(espresso["stages"][stage], normal["stages"][stage])
		self.assertEqual(espresso["trace"][:-2], normal["trace"][:-2])
		self.assertEqual(espresso["events"][:-2], normal["events"][:-2])
		self.assertEqual(espresso["oee"], normal["oee"])
		self.assertEqual(espresso["counter_readings"], normal["counter_readings"])
		espresso["trace"][0]["label"] = "Changed copy"
		self.assertEqual(normal, before)
		with self.assertRaises(ValueError):
			make_espresso_scenario(make_scenario("moisture_hold"))

	def test_portable_build_includes_fifth_scenario_and_espresso_export(self):
		self.assertEqual(SCENARIO_IDS, ("normal", "moisture_hold", "network_gap", "recall", "espresso_pid"))
		with tempfile.TemporaryDirectory() as folder:
			data = build(folder)
			self.assertEqual(tuple(s["id"] for s in data["scenarios"]), SCENARIO_IDS)
			self.assertEqual(len(list(Path(folder).glob("*.ocel.json"))), 5)
			exported = json.loads((Path(folder) / "espresso_pid.ocel.json").read_text(encoding="utf-8"))
			self.assertIn("DEMO-ESPRESSO-CUP-01", {o["id"] for o in exported["objects"]})
			json.dumps(data, allow_nan=False)


if __name__ == "__main__":
	unittest.main()
