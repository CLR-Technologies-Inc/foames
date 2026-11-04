# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Shows each machine's state on its ERPNext Workstation.

ERPNext's Workstation carries a status (Production, Off, Idle, Problem, Maintenance, Setup) that
its Plant Floor page displays. With **Show Machine State on Workstations** on, every state change
of a Machine that points at an ERPNext Workstation queues a `Workstation Status` posting through
the outbox, so the Plant Floor shows what the machine reports. The outbox keeps the audit trail
and the permission model every other write to ERPNext has.

A status is only ever the latest one: when a new state arrives before the previous posting ran,
the earlier posting is cancelled rather than performed, so the Workstation never steps through
stale states and a flapping machine does not pile up postings.
"""

from __future__ import annotations

import frappe

from foames.foames_adapters.erpnext import erpnext_installed
from foames.foames_adapters.erpnext.floor import machine_workstations
from foames.foames_adapters.erpnext.postings import workstation_status_for

OPERATION = "Workstation Status"


def sync_enabled() -> bool:
	if not erpnext_installed():
		return False
	settings = frappe.get_cached_doc("ERPNext Adapter Settings")
	return bool(settings.enable_postings and settings.sync_machine_state_to_workstations)


def sequence_group(workstation: str) -> str:
	return f"workstation:{workstation}"


def on_state_changed(machine, previous_state: str | None, state: str, at) -> str | None:
	"""Registered under `foames_machine_state_changed`. Returns the outbox record queued, if any."""
	if not sync_enabled():
		return None
	workstation = machine_workstations([machine.name]).get(machine.name)
	if not workstation:
		return None
	return queue_status(workstation, workstation_status_for(state), at, machine.name)


def queue_status(workstation: str, status: str, at, machine: str | None = None) -> str:
	"""Queue the Workstation's status as of `at`, superseding any status still waiting for it."""
	from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue

	group = sequence_group(workstation)
	waiting = frappe.get_all(
		"ERPNext Outbox",
		filters={"operation": OPERATION, "sequence_group": group, "status": ("in", ("Queued", "Retry"))},
		pluck="name",
	)
	for name in waiting:
		frappe.db.set_value(
			"ERPNext Outbox",
			name,
			{"status": "Cancelled", "last_error": "Superseded by a later status"},
			update_modified=False,
		)
	key = f"{group}:{status}:{frappe.utils.get_datetime(at).isoformat()}"
	return enqueue(
		OPERATION,
		{"workstation": workstation, "status": status},
		key,
		sequence_group=group,
		reference_doctype="Machine" if machine else None,
		reference_name=machine,
	)
