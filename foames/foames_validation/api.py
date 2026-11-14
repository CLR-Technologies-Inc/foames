# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Where each machine and process stands on its qualifications, for the report, the scheduler,
the MCP server and external agents."""

from __future__ import annotations

import frappe
from frappe.utils import cint, getdate, nowdate

from foames.foames_validation import qualification as q


def subject_of(protocol_type: str, machine: str | None, process_name: str | None) -> tuple[str, str]:
	"""("Machine", machine) for an equipment qualification, ("Process", process) for PPQ and CPV."""
	if protocol_type in q.EQUIPMENT_TYPES:
		return "Machine", machine
	return "Process", process_name


def _approved_executions(filters: dict | None = None) -> list[dict]:
	return frappe.get_all(
		"Validation Execution",
		filters={"docstatus": 1, **(filters or {})},
		fields=[
			"name",
			"protocol",
			"protocol_type",
			"machine",
			"process_name",
			"outcome",
			"reviewed_on",
			"qualified_until",
		],
		order_by="reviewed_on asc, creation asc",
	)


def _required_runs(protocol: str) -> int:
	return max(cint(frappe.db.get_value("Validation Protocol", protocol, "required_runs")), 1)


def _status(executions: list[dict], today, due_soon_days: int) -> dict:
	required = _required_runs(executions[-1]["protocol"]) if executions else 1
	return q.qualification_status(
		[
			{
				"name": e["name"],
				"protocol": e["protocol"],
				"outcome": e["outcome"],
				"approved_on": e["reviewed_on"],
				"qualified_until": getdate(e["qualified_until"]) if e["qualified_until"] else None,
			}
			for e in executions
		],
		today,
		required_runs=required,
		due_soon_days=due_soon_days,
	)


def subject_status(
	subject_type: str, subject: str, protocol_type: str, today=None, due_soon_days=q.DEFAULT_DUE_SOON_DAYS
) -> dict:
	"""The qualification status of one machine or process for one protocol type."""
	field = "machine" if subject_type == "Machine" else "process_name"
	executions = _approved_executions({"protocol_type": protocol_type, field: subject})
	return _status(executions, getdate(today or nowdate()), due_soon_days)


def qualification_rows(
	today=None,
	machine: str | None = None,
	process: str | None = None,
	protocol_type: str | None = None,
	due_soon_days: int = q.DEFAULT_DUE_SOON_DAYS,
) -> list[dict]:
	"""One row per subject and protocol type that has an approved protocol, with its status."""
	today = getdate(today or nowdate())
	protocol_filters = {"docstatus": 1}
	if protocol_type:
		protocol_filters["protocol_type"] = protocol_type
	subjects: dict[tuple, dict] = {}
	for p in frappe.get_all(
		"Validation Protocol",
		filters=protocol_filters,
		fields=["name", "protocol_type", "machine", "process_name", "approved_on"],
		order_by="approved_on asc, creation asc",
	):
		subject_type, subject = subject_of(p.protocol_type, p.machine, p.process_name)
		if subject:
			subjects[(subject_type, subject, p.protocol_type)] = {"protocol": p.name, "executions": []}
	execution_filters = {"protocol_type": protocol_type} if protocol_type else {}
	for e in _approved_executions(execution_filters):
		subject_type, subject = subject_of(e.protocol_type, e.machine, e.process_name)
		if not subject:
			continue
		entry = subjects.setdefault(
			(subject_type, subject, e.protocol_type), {"protocol": e.protocol, "executions": []}
		)
		entry["executions"].append(e)
	rows = []
	for (subject_type, subject, code), entry in sorted(subjects.items()):
		if machine and not (subject_type == "Machine" and subject == machine):
			continue
		if process and not (subject_type == "Process" and subject == process):
			continue
		status = _status(entry["executions"], today, due_soon_days)
		rows.append(
			{
				"subject_type": subject_type,
				"subject": subject,
				"protocol_type": code,
				"protocol_name": q.protocol_type(code)["name"],
				"protocol": entry["executions"][-1]["protocol"] if entry["executions"] else entry["protocol"],
				**status,
			}
		)
	return rows


@frappe.whitelist()
def get_qualification_status(
	machine: str | None = None, process: str | None = None, protocol_type: str | None = None
) -> list[dict]:
	"""Qualification status per machine or process and protocol type: Qualified, Due Soon, Expired,
	Runs Pending or Not Qualified, with the date it lapses and the execution it rests on."""
	frappe.has_permission("Validation Execution", "read", throw=True)
	rows = qualification_rows(machine=machine, process=process, protocol_type=protocol_type)
	for row in rows:
		row["qualified_until"] = str(row["qualified_until"]) if row["qualified_until"] else None
	return rows
