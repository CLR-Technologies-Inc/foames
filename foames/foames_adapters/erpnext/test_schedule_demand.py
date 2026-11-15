# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Job Cards as schedule rows, without a site."""

import unittest
from datetime import datetime

from foames.foames_adapters.erpnext.schedule_demand import demand_rows, unmapped_workstations

DUE = datetime(2026, 11, 20, 17, 0)


def card(name, wo, seq, **kw):
	values = {
		"name": name,
		"work_order": wo,
		"operation": f"Op {seq}",
		"workstation": "WS-1",
		"for_quantity": 100,
		"total_completed_qty": 0,
		"time_required": 120,
		"sequence_id": seq,
	}
	values.update(kw)
	return values


class TestScheduleDemand(unittest.TestCase):
	def test_rows_follow_work_order_and_sequence(self):
		cards = [card("JC-2", "WO-1", 2), card("JC-1", "WO-1", 1), card("JC-3", "WO-0", 1)]
		rows = demand_rows(
			cards,
			{"WO-1": {"expected_delivery_date": DUE, "production_item": "WIDGET"}},
			{"WS-1": ["M1", "M2"]},
			{"JC-1": "REF-1"},
		)
		self.assertEqual([(r["job"], r["sequence"]) for r in rows], [("WO-0", 1), ("WO-1", 1), ("WO-1", 2)])
		first = rows[1]
		self.assertEqual(first["machines"], "M1\nM2")
		self.assertEqual(first["due_date"], DUE)
		self.assertEqual(first["job_reference"], "REF-1")
		self.assertEqual(first["setup_group"], "WIDGET")
		self.assertEqual(first["source"], "ERPNext")

	def test_run_time_is_scaled_to_the_open_quantity(self):
		rows = demand_rows([card("JC-1", "WO-1", 1, total_completed_qty=25)], {}, {})
		self.assertEqual(rows[0]["quantity"], 75)
		self.assertAlmostEqual(rows[0]["run_minutes"], 90)

	def test_finished_cards_are_left_out(self):
		self.assertEqual(demand_rows([card("JC-1", "WO-1", 1, total_completed_qty=100)], {}, {}), [])

	def test_no_time_required_leaves_the_cycle_time_to_foames(self):
		rows = demand_rows(
			[card("JC-1", "WO-1", 1, time_required=0)], {"WO-1": {"planned_end_date": DUE}}, {}
		)
		self.assertIsNone(rows[0]["run_minutes"])
		self.assertEqual(rows[0]["due_date"], DUE)

	def test_unmapped_workstations(self):
		cards = [card("JC-1", "WO-1", 1), card("JC-2", "WO-1", 2, workstation="WS-2")]
		self.assertEqual(unmapped_workstations(cards, {"WS-1": ["M1"]}), ["WS-2"])


if __name__ == "__main__":
	unittest.main()
