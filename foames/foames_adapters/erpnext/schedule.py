# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""ERPNext as a demand source for FoaMES Production Schedules.

Registered under `foames_schedule_demand_sources`. It reads the open Job Cards on the Workstations
that FoaMES Machines are mapped to, and turns them into schedule rows (see `schedule_demand.py`).
It only reads ERPNext; the External Reference of each Job Card is created in FoaMES when missing, so
a machine already working on the card keeps it in the plan.
"""

from __future__ import annotations

import frappe

from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed
from foames.foames_adapters.erpnext.schedule_demand import demand_rows

CARD_FIELDS = (
	"name",
	"work_order",
	"operation",
	"workstation",
	"production_item",
	"for_quantity",
	"total_completed_qty",
	"time_required",
	"sequence_id",
	"status",
	"docstatus",
)
WORK_ORDER_FIELDS = (
	"name",
	"production_item",
	"expected_delivery_date",
	"planned_start_date",
	"planned_end_date",
)


def machines_by_workstation(line: str | None = None) -> dict[str, list[str]]:
	"""ERPNext Workstation -> the enabled FoaMES Machines mapped to it (on `line` when given)."""
	from foames.foames_adapters.erpnext.floor import machine_workstations

	filters = {"disabled": 0}
	if line:
		filters["line"] = line
	machines = frappe.get_all("Machine", filters=filters, pluck="name", order_by="name")
	out: dict[str, list[str]] = {}
	for machine, workstation in machine_workstations(machines).items():
		out.setdefault(workstation, []).append(machine)
	return out


def demand(start=None, end=None, line: str | None = None) -> list[dict]:
	"""Production Schedule Job values for the open Job Cards on mapped Workstations."""
	if not erpnext_installed():
		return []
	from foames.foames_adapters.erpnext.details import _has_column, open_job_cards
	from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

	by_workstation = machines_by_workstation(line)
	if not by_workstation:
		return []
	names = [c["name"] for c in open_job_cards(sorted(by_workstation), limit=0)]
	if not names:
		return []
	fields = [f for f in CARD_FIELDS if _has_column("Job Card", f)]
	cards = frappe.get_all("Job Card", filters={"name": ("in", names)}, fields=fields)
	order_names = sorted({c.work_order for c in cards if c.get("work_order")})
	work_orders = {}
	if order_names:
		wo_fields = [f for f in WORK_ORDER_FIELDS if _has_column("Work Order", f)]
		work_orders = {
			w.name: w
			for w in frappe.get_all("Work Order", filters={"name": ("in", order_names)}, fields=wo_fields)
		}
	references = {
		c.name: get_reference("Job Card", c.name, ADAPTER_KEY, ignore_permissions=True) for c in cards
	}
	return demand_rows(cards, work_orders, by_workstation, references)
