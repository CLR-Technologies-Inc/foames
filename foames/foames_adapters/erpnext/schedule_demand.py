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

"""Open ERPNext Job Cards as rows of a FoaMES Production Schedule. Pure: no Frappe dependency.

One row per Job Card that still has quantity to make. The job is the card's Work Order, so the
cards of one order run in their sequence; the machines are the FoaMES Machines mapped to the card's
Workstation; the run time is the card's own Expected Time Required, scaled to the quantity still
open; the due date is the Work Order's Expected Delivery Date, else its Planned End Date.
"""

from __future__ import annotations

SOURCE = "ERPNext"


def demand_rows(
	cards: list[dict],
	work_orders: dict[str, dict],
	machines_by_workstation: dict[str, list[str]],
	references: dict[str, str] | None = None,
) -> list[dict]:
	"""Production Schedule Job values for `cards`.

	`work_orders` maps a Work Order name to its row (expected_delivery_date, planned_end_date,
	planned_start_date, production_item); `machines_by_workstation` maps an ERPNext Workstation to the
	FoaMES Machines on it; `references` maps a Job Card name to its External Reference."""
	references = references or {}
	rows = []
	for card in sorted(
		cards, key=lambda c: (c.get("work_order") or "", c.get("sequence_id") or 0, c.get("name"))
	):
		planned = float(card.get("for_quantity") or 0)
		remaining = planned - float(card.get("total_completed_qty") or 0)
		if planned > 0 and remaining <= 0:
			continue
		wo = work_orders.get(card.get("work_order")) or {}
		required = float(card.get("time_required") or 0)
		run_minutes = None
		if required > 0:
			run_minutes = required * (remaining / planned if planned > 0 else 1.0)
		machines = machines_by_workstation.get(card.get("workstation")) or []
		item = card.get("production_item") or wo.get("production_item")
		rows.append(
			{
				"job": card.get("work_order") or card["name"],
				"operation": card.get("operation") or card["name"],
				"sequence": int(card.get("sequence_id") or 0) or 10,
				"quantity": max(remaining, 0.0),
				"run_minutes": round(run_minutes, 4) if run_minutes is not None else None,
				"due_date": wo.get("expected_delivery_date") or wo.get("planned_end_date"),
				"release_date": wo.get("planned_start_date"),
				"machines": "\n".join(machines),
				"setup_group": item,
				"job_reference": references.get(card["name"]),
				"source": SOURCE,
			}
		)
	return rows


def unmapped_workstations(cards: list[dict], machines_by_workstation: dict[str, list[str]]) -> list[str]:
	"""Workstations of `cards` that no FoaMES Machine is mapped to."""
	return sorted(
		{c.get("workstation") for c in cards if c.get("workstation")} - set(machines_by_workstation)
	)
