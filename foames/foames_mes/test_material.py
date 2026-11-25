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

"""Material flow arithmetic: MPC, lineside stock, kanban, the line-dry forecast and queues. No Frappe site needed."""

import unittest
from datetime import datetime, timedelta

from foames.foames_mes.material import (
	FACTORS,
	assess_bin,
	bin_findings,
	consumption,
	dispatch_order,
	estimated_on_hand,
	factor_scores,
	hours_to_dry,
	kanban_cards,
	mpc,
	numeric_score,
	queue_findings,
	queue_summary,
	rate_per_hour,
	readiness,
	replenish_quantity,
)

NOW = datetime(2026, 11, 16, 12, 0, 0)


def ago(minutes):
	return NOW - timedelta(minutes=minutes)


class TestMPC(unittest.TestCase):
	def test_blank_profile_is_standard(self):
		result = mpc({})
		self.assertEqual(result["level"], 1)
		self.assertEqual(result["label"], "Standard")
		self.assertEqual(result["expert_oversight"], "none")
		self.assertEqual(result["drivers"], [])
		self.assertEqual(result["default_dispatch"], "FIFO")

	def test_highest_factor_sets_level(self):
		self.assertEqual(mpc({"storage_temperature": "Controlled room temperature"})["level"], 2)
		self.assertEqual(mpc({"esd_sensitivity": "ESD sensitive"})["level"], 3)
		self.assertEqual(mpc({"atmosphere": "Dry room"})["level"], 4)
		self.assertEqual(mpc({"exposure_band": "OEB 5"})["level"], 5)

	def test_top_levels_need_experts(self):
		four = mpc({"storage_temperature": "Frozen"})
		self.assertEqual(four["level"], 4)
		self.assertEqual(four["expert_oversight"], "single")
		self.assertIn("Human Expert Recommended", four["label"])
		five = mpc({"hazard_rating": "4 - Severe"})
		self.assertEqual(five["expert_oversight"], "team")
		self.assertEqual(five["drivers"], ["hazard_rating"])

	def test_three_elevated_factors_compound(self):
		profile = {
			"storage_temperature": "Refrigerated (2-8 C)",
			"cleanliness": "ISO 7",
			"physical_form": "Cohesive powder, paste or viscous liquid",
		}
		result = mpc(profile)
		self.assertTrue(result["compounded"])
		self.assertEqual(result["level"], 4)
		two = mpc({"storage_temperature": "Refrigerated (2-8 C)", "cleanliness": "ISO 7"})
		self.assertFalse(two["compounded"])
		self.assertEqual(two["level"], 3)

	def test_compounding_stops_at_five(self):
		profile = {"hazard_rating": "4 - Severe", "exposure_band": "OEB 4", "cleanliness": "ISO 5"}
		self.assertEqual(mpc(profile)["level"], 5)

	def test_time_limits_score_by_band(self):
		self.assertEqual(numeric_score("shortest_time_limit_hours", 0), 0)
		self.assertEqual(numeric_score("shortest_time_limit_hours", 0.5), 4)
		self.assertEqual(numeric_score("shortest_time_limit_hours", 8), 3)
		self.assertEqual(numeric_score("shortest_time_limit_hours", 168), 2)
		self.assertEqual(numeric_score("shortest_time_limit_hours", 8760), 1)

	def test_time_sensitive_material_dispatches_first_expired_first_out(self):
		self.assertEqual(mpc({"shortest_time_limit_hours": 72})["default_dispatch"], "Earliest Expiry")
		self.assertEqual(mpc({"moisture_sensitivity": "MSL 3"})["default_dispatch"], "Earliest Expiry")

	def test_moisture_sensitivity_follows_jstd033(self):
		self.assertEqual(mpc({"moisture_sensitivity": "MSL 1"})["level"], 1)
		self.assertEqual(mpc({"moisture_sensitivity": "MSL 3"})["level"], 3)
		self.assertEqual(mpc({"moisture_sensitivity": "MSL 6"})["level"], 5)

	def test_unknown_option_scores_zero(self):
		self.assertEqual(factor_scores({"hazard_rating": "nonsense"})["hazard_rating"], 0)

	def test_every_factor_names_a_source(self):
		for spec in FACTORS.values():
			self.assertTrue(spec["source"])
			self.assertIn(0, spec["options"].values())


class TestLinesideStock(unittest.TestCase):
	def test_consumption_and_estimate(self):
		self.assertAlmostEqual(consumption(100, 0.25), 25.0)
		self.assertAlmostEqual(consumption(100, 0.25, 4), 26.0)
		self.assertEqual(consumption(-5, 1), 0.0)
		self.assertAlmostEqual(estimated_on_hand(40, 25), 15.0)
		self.assertEqual(estimated_on_hand(10, 25), 0.0)

	def test_rate_and_hours(self):
		self.assertAlmostEqual(rate_per_hour(30, 2), 15.0)
		self.assertEqual(rate_per_hour(30, 0), 0.0)
		self.assertIsNone(hours_to_dry(10, 0))
		self.assertAlmostEqual(hours_to_dry(30, 15), 2.0)

	def test_kanban_cards(self):
		# 60 an hour over a 2 hour loop with 10 percent safety, in containers of 25: 132 / 25 -> 6 cards.
		self.assertEqual(kanban_cards(60, 2, 25, 10), 6)
		self.assertEqual(kanban_cards(50, 2, 25), 4)
		self.assertEqual(kanban_cards(0, 2, 25), 1)
		with self.assertRaises(ValueError):
			kanban_cards(10, 1, 0)

	def test_replenish_by_method(self):
		self.assertEqual(replenish_quantity({"reorder_qty": 20, "max_qty": 100}, 30), 0)
		self.assertEqual(
			replenish_quantity({"replenishment_method": "Min-Max", "reorder_qty": 20, "max_qty": 100}, 15), 85
		)
		self.assertEqual(
			replenish_quantity(
				{"replenishment_method": "Min-Max", "reorder_qty": 20, "max_qty": 100, "in_transit_qty": 10},
				5,
			),
			85,
		)
		self.assertEqual(replenish_quantity({"reorder_qty": 20, "container_qty": 50}, 10), 50)
		kanban = {"replenishment_method": "Kanban", "container_qty": 25, "kanban_cards": 4}
		self.assertEqual(replenish_quantity(kanban, 60), 50)  # two full containers, two cards back
		self.assertEqual(replenish_quantity(kanban, 100), 0)

	def test_bin_statuses(self):
		b = {"replenishment_lead_minutes": 120, "reorder_qty": 50}
		self.assertEqual(assess_bin(b, 0, 10)["status"], "Dry")
		self.assertEqual(assess_bin(b, 15, 10)["status"], "Will Run Dry")  # 1.5 h left, 2 h lead
		self.assertEqual(assess_bin(b, 25, 10)["status"], "Running Dry")  # 2.5 h left, 3 h horizon
		self.assertEqual(assess_bin(b, 45, 10)["status"], "Reorder")
		self.assertEqual(assess_bin(b, 100, 10)["status"], "OK")
		self.assertEqual(assess_bin(b, 45, 0)["status"], "Reorder")  # not consuming: no dry forecast

	def test_material_in_transit_holds_off_the_dry_warning(self):
		b = {"replenishment_lead_minutes": 120, "reorder_qty": 50, "in_transit_qty": 50}
		self.assertEqual(assess_bin(b, 15, 10)["status"], "OK")

	def test_conditioning_time_and_mpc_widen_the_horizon(self):
		b = {"replenishment_lead_minutes": 60, "reorder_qty": 0}
		self.assertEqual(assess_bin(b, 20, 10)["status"], "OK")  # 2 h left, 1.5 h horizon
		thawed = assess_bin(b, 20, 10, conditioning_minutes=90)  # 2.5 h lead with thawing
		self.assertEqual(thawed["status"], "Will Run Dry")
		critical = assess_bin(b, 20, 10, mpc_level=5)  # 1 h x 2.0 x 1.5 = 3 h horizon
		self.assertEqual(critical["status"], "Running Dry")
		self.assertAlmostEqual(critical["horizon_hours"], 3.0)

	def test_bin_findings(self):
		b = {
			"replenishment_lead_minutes": 120,
			"reorder_qty": 50,
			"max_qty": 200,
			"replenishment_method": "Min-Max",
		}
		rows = [
			{
				"name": "LSB-00001",
				"title": "Resin A",
				"machine": "MOULD-1",
				"item": "RES-A",
				"uom": "kg",
				"mpc_level": 4,
				"assessment": assess_bin(b, 15, 10),
				"dry_at": NOW + timedelta(hours=1.5),
				"cycle": "2026-11-16 06:00:00",
			},
			{"name": "LSB-00002", "assessment": assess_bin(b, 500, 10)},
		]
		found = bin_findings(rows)
		self.assertEqual(len(found), 1)
		f = found[0]
		self.assertEqual(f["severity"], "Critical")
		self.assertEqual(f["category"], "Material")
		self.assertEqual(f["reference_doctype"], "Lineside Bin")
		self.assertIn("MPC 4", f["suggestion"])
		self.assertIn("185.00 kg", f["suggestion"])
		self.assertEqual(f["rule_key"], "material-bin:LSB-00001:Will Run Dry:2026-11-16 06:00:00")


class TestQueues(unittest.TestCase):
	def test_readiness_states(self):
		self.assertEqual(
			readiness({"arrived_at": ago(5), "min_wait_minutes": 30}, NOW)["state"], "Conditioning"
		)
		self.assertEqual(readiness({"arrived_at": ago(40), "min_wait_minutes": 30}, NOW)["state"], "Ready")
		self.assertEqual(
			readiness({"arrived_at": ago(85), "max_wait_minutes": 100}, NOW)["state"], "Q-time Warning"
		)
		self.assertEqual(
			readiness({"arrived_at": ago(100), "max_wait_minutes": 100}, NOW)["state"], "Q-time Exceeded"
		)
		self.assertEqual(readiness({"arrived_at": ago(1), "expires_at": ago(0)}, NOW)["state"], "Expired")
		self.assertEqual(readiness({"arrived_at": ago(500), "status": "On Hold"}, NOW)["state"], "On Hold")
		self.assertEqual(
			readiness({"arrived_at": ago(10), "max_wait_minutes": 100}, NOW, 5)["state"], "Q-time Warning"
		)

	def test_readiness_accepts_strings(self):
		r = readiness({"arrived_at": "2026-11-16 11:00:00", "max_wait_minutes": 120}, NOW)
		self.assertEqual(r["state"], "Ready")
		self.assertAlmostEqual(r["minutes_to_limit"], 60.0)

	def test_dispatch_rules(self):
		entries = [
			{"name": "A", "arrived_at": ago(60), "priority": 1, "due_at": NOW + timedelta(hours=5)},
			{
				"name": "B",
				"arrived_at": ago(30),
				"priority": 5,
				"due_at": NOW + timedelta(hours=1),
				"max_wait_minutes": 40,
			},
			{"name": "C", "arrived_at": ago(10), "priority": 5, "min_wait_minutes": 30},
			{"name": "D", "arrived_at": ago(90), "expires_at": ago(1)},
			{"name": "E", "arrived_at": ago(20), "priority": 3, "expires_at": NOW + timedelta(minutes=5)},
		]
		names = lambda rule: [e["name"] for e in dispatch_order(entries, rule, NOW)]  # noqa: E731
		self.assertEqual(names("FIFO"), ["A", "B", "E"])  # C conditioning, D expired
		self.assertEqual(names("Priority"), ["B", "E", "A"])
		self.assertEqual(names("Earliest Due"), ["B", "A", "E"])
		self.assertEqual(names("Earliest Expiry"), ["E", "B", "A"])

	def test_summary_starved_and_full(self):
		q = {"capacity": 2}
		entries = [
			{"name": "A", "arrived_at": ago(5), "min_wait_minutes": 30, "quantity": 4},
			{"name": "B", "arrived_at": ago(2), "min_wait_minutes": 30, "quantity": 6},
			{"name": "Z", "arrived_at": ago(50), "status": "Done"},
		]
		s = queue_summary(q, entries, NOW)
		self.assertEqual(s["waiting"], 2)
		self.assertEqual(s["ready"], 0)
		self.assertTrue(s["starved"])
		self.assertTrue(s["full"])
		self.assertAlmostEqual(s["quantity"], 10)
		running = queue_summary(
			q, [*entries, {"name": "C", "arrived_at": ago(60), "status": "In Process"}], NOW
		)
		self.assertFalse(running["starved"])

	def test_queue_findings(self):
		queues = [
			{
				"name": "MQ-0001",
				"title": "Cure oven queue",
				"machine": "OVEN-1",
				"machine_status": "Idle",
				"capacity": 2,
				"last_activity": "2026-11-16 10:00:00",
				"entries": [
					{
						"name": "MQE-1",
						"item": "PANEL",
						"quantity": 4,
						"arrived_at": ago(130),
						"max_wait_minutes": 120,
						"batch": "L-7",
					},
					{
						"name": "MQE-2",
						"item": "PANEL",
						"arrived_at": ago(5),
						"min_wait_minutes": 30,
						"mpc_level": 5,
					},
				],
			}
		]
		found = {f["rule_key"]: f for f in queue_findings(queues, NOW)}
		self.assertIn("material-queue:MQE-1:Q-time Exceeded", found)
		self.assertEqual(found["material-queue:MQE-1:Q-time Exceeded"]["severity"], "Critical")
		self.assertIn("lot L-7", found["material-queue:MQE-1:Q-time Exceeded"]["suggestion"])
		self.assertIn("material-starved:MQ-0001:2026-11-16 10:00:00", found)
		self.assertIn(
			"still conditioning", found["material-starved:MQ-0001:2026-11-16 10:00:00"]["suggestion"]
		)
		self.assertIn("material-blocked:MQ-0001:MQE-1", found)

	def test_down_machine_is_not_reported_starved(self):
		queues = [{"name": "MQ-2", "machine": "M", "machine_status": "Down", "entries": []}]
		self.assertEqual(queue_findings(queues, NOW), [])


if __name__ == "__main__":
	unittest.main()
