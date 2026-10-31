# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""ERPNext work on the floor: the open Job Cards and Work Orders of each machine's workstation,
added to the floor snapshot, and a rule built on them.

A Machine points at its ERPNext Workstation through `workstation_reference` (an External Reference
of type Workstation). The snapshot section is keyed by machine, so the floor page, the rules and
an external agent see which job a machine should be running next to its live state and counts.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, get_datetime

from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed


def floor_enabled() -> bool:
	if not erpnext_installed():
		return False
	return bool(frappe.db.get_single_value("ERPNext Adapter Settings", "show_job_cards_on_floor"))


def extend_snapshot(snapshot: dict, since, now):
	"""Registered under `foames_floor_snapshot_extensions`. Adds `job_cards` to each machine with a
	workstation reference, and an `erp` section with the open Work Orders and totals."""
	if not floor_enabled():
		return
	from foames.foames_adapters.erpnext.details import open_job_cards, open_work_orders

	workstation_by_machine = machine_workstations([m["name"] for m in snapshot.get("machines", [])])
	workstations = sorted(set(workstation_by_machine.values()))
	lookahead = frappe.db.get_single_value("ERPNext Adapter Settings", "floor_lookahead_days")
	# Look-ahead 0 means "due by now", 2 means "due within the next two days"; a card with no
	# expected start is always shown. The snapshot is per machine, so no page limit applies.
	horizon = add_days(now, int(lookahead or 0))
	job_cards = [
		jc
		for jc in open_job_cards(workstations, limit=0)
		if not jc.get("expected_start_date") or get_datetime(jc["expected_start_date"]) <= horizon
	]
	by_workstation: dict[str, list[dict]] = {}
	for jc in job_cards:
		by_workstation.setdefault(jc["workstation"], []).append(jc)
	for m in snapshot.get("machines", []):
		workstation = workstation_by_machine.get(m["name"])
		m["workstation"] = workstation
		m["job_cards"] = by_workstation.get(workstation, []) if workstation else []
	snapshot["erp"] = {
		"system": ADAPTER_KEY,
		"open_work_orders": open_work_orders(),
		"open_job_cards": len(job_cards),
		"unmapped_machines": [m["name"] for m in snapshot.get("machines", []) if not m.get("workstation")],
	}


def machine_workstations(machines: list[str]) -> dict[str, str]:
	"""Machine name -> ERPNext Workstation name, for machines whose reference points at ERPNext."""
	if not machines:
		return {}
	rows = frappe.get_all(
		"Machine",
		filters={"name": ("in", machines), "workstation_reference": ("is", "set")},
		fields=["name", "workstation_reference"],
	)
	if not rows:
		return {}
	references = {
		r.name: r.external_id
		for r in frappe.get_all(
			"External Reference",
			filters={
				"name": ("in", [r.workstation_reference for r in rows]),
				"erp_system": ADAPTER_KEY,
				"reference_type": "Workstation",
				"status": ("!=", "Missing"),
			},
			fields=["name", "external_id"],
		)
	}
	return {
		r.name: references[r.workstation_reference] for r in rows if r.workstation_reference in references
	}


def running_without_job_card(snapshot: dict) -> list[dict]:
	"""Registered under `foames_suggestion_rules`: a machine that reports Running while its ERPNext
	workstation has no open Job Card is producing against nothing ERPNext knows about."""
	if "erp" not in snapshot:
		return []
	out = []
	for m in snapshot.get("machines", []):
		if m.get("status") != "Running" or not m.get("workstation") or m.get("job_cards"):
			continue
		out.append(
			{
				"rule_key": f"erpnext-no-job-card:{m['name']}:{m.get('last_seen')}",
				"category": "ERP",
				"severity": "Warning",
				"title": f"{m['name']} is running with no open Job Card on {m['workstation']}",
				"suggestion": (
					f"Machine {m['name']} reports Running, but workstation {m['workstation']} has no open "
					"Job Card in ERPNext. Either the Work Order was not released, the Job Card is on another "
					"workstation, or the machine is running an unplanned job. Check before the counts are lost."
				),
				"reference_doctype": "Machine",
				"reference_name": m["name"],
				"evidence": {
					"workstation": m["workstation"],
					"status": m.get("status"),
					"counts": m.get("counts"),
				},
			}
		)
	return out
