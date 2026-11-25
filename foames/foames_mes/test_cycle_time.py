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

"""Automatic and manual time arithmetic: the cycle split, projections, scenarios, observed time and
calibration. No Frappe site needed."""

import json
import unittest

from foames.foames_mes.cycle_time import (
	Element,
	Standard,
	apply_changes,
	breakdown,
	calibrate,
	compare,
	observed,
	problems,
	project,
	standard_from_dict,
	variance,
)

# A lathe operation, worked by hand below:
# external manual (machine stopped): load 20 + unload 10 = 30 s, x 1.10 allowance = 33 s
# internal manual (while it cuts): deburr 25 + gauge 60 every 10 cycles = 31 s, x 1.10 = 34.1 s
# automatic: cut 90 s
# cycle = 33 + max(90, 34.1) = 123 s; operator = 67.1 s; machines per operator = 123 / 67.1
LATHE = Standard(
	name="CTS-LATHE",
	parts_per_cycle=1,
	allowance_percent=10,
	labor_rate=36.0,
	machine_rate=72.0,
	elements=(
		Element("Load", "Manual", 20),
		Element("Cut", "Automatic", 90),
		Element("Unload", "Manual", 10),
		Element("Deburr previous part", "Manual", 25, internal=True),
		Element("Gauge check", "Manual", 60, internal=True, every=10),
		Element("Setup", "Manual", 1800, per="Batch"),
		Element("Warm-up", "Automatic", 300, per="Batch"),
	),
)


class TestBreakdown(unittest.TestCase):
	def test_lathe_cycle(self):
		b = breakdown(LATHE)
		self.assertAlmostEqual(b.manual_external, 33.0)
		self.assertAlmostEqual(b.manual_internal, 34.1)
		self.assertAlmostEqual(b.automatic, 90.0)
		self.assertAlmostEqual(b.cycle, 123.0)
		self.assertAlmostEqual(b.operator, 67.1)
		self.assertAlmostEqual(b.operator_waits, 55.9)
		self.assertEqual(b.machine_waits, 0.0)
		self.assertAlmostEqual(b.machines_per_operator, 123.0 / 67.1)
		self.assertAlmostEqual(b.setup_manual, 1980.0)  # allowance applies to manual batch work
		self.assertAlmostEqual(b.setup_automatic, 300.0)  # and not to machine time
		self.assertAlmostEqual(b.as_dict()["automation_percent"], 90.0 / 123.0 * 100.0)

	def test_internal_work_longer_than_the_machine_makes_it_wait(self):
		std = Standard(
			elements=(Element("Cut", "Automatic", 20), Element("Inspect", "Manual", 30, internal=True))
		)
		b = breakdown(std)
		self.assertEqual(b.cycle, 30.0)
		self.assertEqual(b.machine_waits, 10.0)
		self.assertEqual(b.operator_waits, 0.0)
		self.assertTrue(any("waits for the operator" in n for n in b.notes))

	def test_fully_automatic_has_no_operator_limit(self):
		b = breakdown(Standard(elements=(Element("Mould", "Automatic", 40),)))
		self.assertEqual(b.cycle, 40.0)
		self.assertIsNone(b.machines_per_operator)
		self.assertEqual(b.as_dict()["automation_percent"], 100.0)
		json.dumps(b.as_dict())  # no Infinity or NaN in what the API returns

	def test_fully_manual(self):
		b = breakdown(Standard(elements=(Element("Assemble", "Manual", 120),)))
		self.assertEqual(b.cycle, 120.0)
		self.assertEqual(b.machines_per_operator, 1.0)
		self.assertEqual(b.as_dict()["automation_percent"], 0.0)


class TestProblems(unittest.TestCase):
	def test_lathe_is_valid(self):
		self.assertEqual(problems(LATHE), [])

	def test_each_problem_is_named(self):
		bad = Standard(
			parts_per_cycle=0,
			allowance_percent=-5,
			elements=(
				Element("A", "Robot", 10),
				Element("A", "Manual", -1, per="Shift", every=0),
			),
		)
		text = " ".join(problems(bad))
		for fragment in (
			"parts per cycle",
			"allowance",
			"kind must be",
			"per must be",
			"cannot be negative",
			"every N cycles",
			"unique",
		):
			self.assertIn(fragment, text)

	def test_batch_only_standard_has_no_cycle(self):
		self.assertIn(
			"no element with time per cycle",
			" ".join(problems(Standard(elements=(Element("Setup", "Manual", 600, per="Batch"),)))),
		)


class TestProject(unittest.TestCase):
	def test_lathe_hundred_parts(self):
		p = project(LATHE, 100)
		self.assertEqual(p["cycles"], 100)
		self.assertAlmostEqual(p["setup_minutes"], (1980 + 300) / 60)
		self.assertAlmostEqual(p["run_minutes"], 12300 / 60)
		self.assertAlmostEqual(p["elapsed_minutes"], 14580 / 60)
		self.assertAlmostEqual(p["automatic_minutes"], 9300 / 60)
		self.assertAlmostEqual(p["operator_minutes"], 8690 / 60)
		self.assertAlmostEqual(p["parts_per_hour"], 100 / (14580 / 3600))
		self.assertAlmostEqual(p["labor_cost"], 8690 / 3600 * 36)
		self.assertAlmostEqual(p["machine_cost"], 14580 / 3600 * 72)
		self.assertAlmostEqual(p["cost_per_part"], (p["labor_cost"] + p["machine_cost"]) / 100)
		json.dumps(p)

	def test_whole_cycles(self):
		std = Standard(parts_per_cycle=2, elements=(Element("Press", "Automatic", 10),))
		self.assertEqual(project(std, 7)["cycles"], 4)
		self.assertEqual(project(std, 8)["cycles"], 4)

	def test_zero_quantity_is_batch_time_only(self):
		p = project(LATHE, 0)
		self.assertEqual(p["cycles"], 0)
		self.assertAlmostEqual(p["elapsed_minutes"], 2280 / 60)
		self.assertEqual(p["cost_per_part"], 0.0)
		self.assertEqual(p["parts_per_hour"], 0.0)


class TestScenarios(unittest.TestCase):
	def test_automating_load_and_unload(self):
		robot = apply_changes(
			LATHE,
			[
				{"element": "Load", "kind": "Automatic", "seconds": 8},
				{"element": "Unload", "kind": "Automatic", "seconds": 6},
			],
		)
		b = breakdown(robot)
		self.assertEqual(b.manual_external, 0.0)
		self.assertAlmostEqual(b.automatic, 104.0)
		self.assertAlmostEqual(b.cycle, 104.0)
		self.assertAlmostEqual(b.operator, 34.1)
		self.assertEqual(breakdown(LATHE).cycle, 123.0)  # the baseline is not changed

		result = compare(project(LATHE, 100), project(robot, 100), annual_quantity=50000)
		self.assertAlmostEqual(result["delta"]["cycle_seconds"], -19.0)
		self.assertAlmostEqual(result["delta"]["operator_minutes"], -(67.1 - 34.1) * 100 / 60)
		self.assertGreater(result["delta"]["automation_percent"], 0)
		self.assertAlmostEqual(result["annual"]["operator_hours_saved"], 33.0 * 50000 / 3600)
		self.assertGreater(result["annual"]["cost_saved"], 0)

	def test_add_remove_and_standard_level_changes(self):
		std = apply_changes(
			LATHE,
			[
				{"element": "Gauge check", "remove": True},
				{"element": "Vision check", "kind": "Automatic", "seconds": 3},
				{"element": "Nonexistent", "remove": True},
				{"parts_per_cycle": 2, "allowance_percent": 0},
			],
		)
		names = [e.name for e in std.elements]
		self.assertNotIn("Gauge check", names)
		self.assertIn("Vision check", names)
		self.assertNotIn("Nonexistent", names)
		self.assertEqual(std.parts_per_cycle, 2.0)
		b = breakdown(std)
		self.assertAlmostEqual(b.automatic, 93.0)
		self.assertAlmostEqual(b.manual_internal, 25.0)

	def test_internal_flag_moves_work_off_the_critical_path(self):
		# SMED-style: doing the unload while the next part cuts.
		std = apply_changes(LATHE, [{"element": "Unload", "internal": True}])
		self.assertAlmostEqual(breakdown(std).cycle, 22.0 + 90.0)


class TestObserved(unittest.TestCase):
	def test_per_cycle_figures(self):
		obs = observed(running_seconds=9500, idle_seconds=3500, setup_seconds=1200, parts=100)
		self.assertEqual(obs["cycles"], 100)
		self.assertEqual(obs["automatic_seconds"], 95.0)
		self.assertEqual(obs["idle_seconds_per_cycle"], 35.0)
		self.assertEqual(obs["cycle_seconds"], 130.0)
		self.assertEqual(obs["setup_minutes"], 20.0)

	def test_parts_per_cycle(self):
		self.assertEqual(observed(1000, 0, 0, parts=100, parts_per_cycle=4)["cycles"], 25)

	def test_no_parts_means_no_per_cycle_figures(self):
		obs = observed(3600, 600, 0, parts=0)
		self.assertIsNone(obs["automatic_seconds"])
		self.assertIsNone(obs["cycle_seconds"])
		json.dumps(obs)

	def test_variance(self):
		self.assertAlmostEqual(variance(90, 99), 10.0)
		self.assertAlmostEqual(variance(90, 81), -10.0)
		self.assertIsNone(variance(90, None))
		self.assertIsNone(variance(0, 10))


class TestCalibrate(unittest.TestCase):
	def test_scales_only_automatic_cycle_elements(self):
		obs = observed(9900, 3000, 0, parts=100)  # 99 s automatic per cycle against 90 s standard
		std, notes = calibrate(LATHE, obs)
		b = breakdown(std)
		self.assertAlmostEqual(b.automatic, 99.0)
		self.assertAlmostEqual(b.manual_external, 33.0)
		self.assertAlmostEqual(b.setup_automatic, 300.0)  # batch time is not observed per cycle
		self.assertIn("1.100", notes[0])

	def test_too_few_cycles_keeps_the_standard(self):
		std, notes = calibrate(LATHE, observed(990, 0, 0, parts=10))
		self.assertIs(std, LATHE)
		self.assertIn("fewer than 20", notes[0])

	def test_no_automatic_elements(self):
		manual = Standard(elements=(Element("Assemble", "Manual", 60),))
		std, notes = calibrate(manual, observed(6000, 0, 0, parts=100))
		self.assertIs(std, manual)
		self.assertIn("no automatic time", notes[0])


class TestFromDict(unittest.TestCase):
	def test_document_rows(self):
		std = standard_from_dict(
			{
				"name": "CTS-00001",
				"parts_per_cycle": 2,
				"allowance_percent": 15,
				"elements": [
					{
						"element_name": "Load",
						"kind": "Manual",
						"seconds": 12,
						"per": "Cycle",
						"internal": 0,
						"every_n_cycles": 1,
					},
					{
						"element_name": "Weld",
						"kind": "Automatic",
						"seconds": 40,
						"per": "Cycle",
						"every_n_cycles": None,
					},
				],
			}
		)
		self.assertEqual(std.name, "CTS-00001")
		self.assertEqual(std.elements[1].every, 1.0)
		self.assertAlmostEqual(breakdown(std).cycle, 12 * 1.15 + 40)


class TestFromDictKeepsZero(unittest.TestCase):
	def test_zero_is_not_replaced_by_the_default(self):
		std = standard_from_dict(
			{
				"parts_per_cycle": 0,
				"elements": [{"element_name": "Cut", "kind": "Automatic", "seconds": 5, "every_n_cycles": 0}],
			}
		)
		self.assertEqual(std.parts_per_cycle, 0.0)
		self.assertEqual(std.elements[0].every, 0.0)
		text = " ".join(problems(std))
		self.assertIn("parts per cycle", text)
		self.assertIn("every N cycles", text)


class TestPurity(unittest.TestCase):
	def test_imports_nothing_from_frappe(self):
		import foames.foames_mes.cycle_time as module

		with open(module.__file__) as f:
			source = f.read()
		self.assertNotIn("import frappe", source)
		self.assertNotIn("from frappe", source)


if __name__ == "__main__":
	unittest.main()
