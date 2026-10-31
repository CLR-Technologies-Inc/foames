# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Read-only whitelisted methods for agents, used by the MCP tools and callable over HTTP.

Every list goes through `frappe.get_list`, so the role and user permissions of the caller apply as
they do on the desk, and every single-record read checks `frappe.has_permission` first. Nothing
here writes.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, now_datetime

from foames.foames_adapters import REFERENCE_TYPES, AdapterError, get_adapter, get_adapters

MAX_LIMIT = 1000

MACHINE_FIELDS = [
	"name",
	"title",
	"machine_type",
	"line",
	"status",
	"last_seen",
	"last_count_at",
	"current_job_reference",
	"current_job_since",
	"disabled",
	"ideal_cycle_seconds",
	"shift_start",
	"scheduled_minutes_per_day",
	"counter_rollover",
	"workstation_reference",
	"location_reference",
]
MACHINE_EVENT_FIELDS = [
	"name",
	"machine",
	"event_type",
	"timestamp",
	"source",
	"state",
	"counter_name",
	"counter_value",
	"delta",
	"measurement_name",
	"value",
	"text",
	"processed",
	"processing_note",
]
DOWNTIME_FIELDS = [
	"name",
	"machine",
	"reason",
	"status",
	"source",
	"start_time",
	"end_time",
	"duration_minutes",
	"notes",
]
OEE_FIELDS = [
	"name",
	"machine",
	"from_time",
	"to_time",
	"planned_minutes",
	"ideal_cycle_seconds",
	"run_minutes",
	"planned_downtime_minutes",
	"unplanned_downtime_minutes",
	"unknown_minutes",
	"coverage",
	"good_count",
	"scrap_count",
	"availability",
	"performance",
	"quality",
	"oee",
]
SUGGESTION_FIELDS = [
	"name",
	"title",
	"category",
	"severity",
	"status",
	"agent",
	"reference_doctype",
	"reference_name",
	"rule_key",
	"creation",
	"resolved_by",
	"resolved_on",
]


def _limit(limit: int | str | None) -> int:
	limit = cint(limit) or 100
	return max(1, min(limit, MAX_LIMIT))


def _window(filters: list, field: str, since: str | None, until: str | None):
	if since:
		filters.append([field, ">=", get_datetime(since)])
	if until:
		filters.append([field, "<", get_datetime(until)])


# Machines ---------------------------------------------------------------------------------------


@frappe.whitelist()
def list_machines(
	status: str | None = None,
	machine_type: str | None = None,
	include_disabled: bool = False,
	limit: int = 100,
) -> list[dict]:
	filters = []
	if not cint(include_disabled):
		filters.append(["disabled", "=", 0])
	if status:
		filters.append(["status", "=", status])
	if machine_type:
		filters.append(["machine_type", "=", machine_type])
	return frappe.get_list(
		"Machine", filters=filters, fields=MACHINE_FIELDS, order_by="name", limit_page_length=_limit(limit)
	)


@frappe.whitelist()
def get_machine(machine: str) -> dict:
	from foames.foames_mes.floor import counts_since

	frappe.has_permission("Machine", "read", machine, throw=True)
	doc = frappe.get_doc("Machine", machine)
	out = {field: doc.get(field) for field in MACHINE_FIELDS}
	out["counts_last_24h"] = counts_since(machine, add_days(now_datetime(), -1))
	if frappe.has_permission("Downtime Record", "read"):
		out["open_downtime"] = frappe.get_list(
			"Downtime Record",
			filters={"machine": machine, "status": "Open"},
			fields=DOWNTIME_FIELDS,
			order_by="start_time desc",
			limit_page_length=1,
		)
	if frappe.has_permission("OEE Period", "read"):
		periods = frappe.get_list(
			"OEE Period",
			filters={"machine": machine},
			fields=OEE_FIELDS,
			order_by="from_time desc",
			limit_page_length=1,
		)
		out["latest_oee_period"] = periods[0] if periods else None
	if frappe.has_permission("Machine Event", "read"):
		out["recent_state_events"] = frappe.get_list(
			"Machine Event",
			filters={"machine": machine, "event_type": ("in", ("State", "Alarm"))},
			fields=["name", "event_type", "state", "timestamp", "source", "text"],
			order_by="timestamp desc",
			limit_page_length=20,
		)
	return out


@frappe.whitelist()
def list_machine_events(
	machine: str | None = None,
	event_type: str | None = None,
	since: str | None = None,
	until: str | None = None,
	limit: int = 100,
) -> list[dict]:
	filters = []
	if machine:
		filters.append(["machine", "=", machine])
	if event_type:
		filters.append(["event_type", "=", event_type])
	_window(filters, "timestamp", since, until)
	return frappe.get_list(
		"Machine Event",
		filters=filters,
		fields=MACHINE_EVENT_FIELDS,
		order_by="timestamp desc, creation desc",
		limit_page_length=_limit(limit),
	)


# Downtime ---------------------------------------------------------------------------------------


@frappe.whitelist()
def list_downtime(
	machine: str | None = None,
	status: str | None = None,
	reason: str | None = None,
	since: str | None = None,
	until: str | None = None,
	limit: int = 100,
) -> list[dict]:
	filters = []
	if machine:
		filters.append(["machine", "=", machine])
	if status:
		filters.append(["status", "=", status])
	if reason:
		filters.append(["reason", "=", reason])
	_window(filters, "start_time", since, until)
	return frappe.get_list(
		"Downtime Record",
		filters=filters,
		fields=DOWNTIME_FIELDS,
		order_by="start_time desc",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def downtime_by_reason(machine: str, since: str | None = None, until: str | None = None) -> dict:
	from foames.foames_mes.floor import downtime_by_reason as minutes_by_reason

	frappe.has_permission("Downtime Record", "read", throw=True)
	frappe.has_permission("Machine", "read", machine, throw=True)
	until = get_datetime(until) if until else now_datetime()
	since = get_datetime(since) if since else add_days(until, -1)
	if until <= since:
		frappe.throw(_("The window must end after it starts"))
	minutes = minutes_by_reason(machine, since, until, ignore_permissions=False)
	classified = {reason: round(value, 2) for reason, value in minutes.items() if reason}
	return {
		"machine": machine,
		"since": since,
		"until": until,
		"total_minutes": round(sum(minutes.values()), 2),
		"unclassified_minutes": round(minutes.get(None, 0), 2),
		"minutes_by_reason": dict(sorted(classified.items(), key=lambda item: -item[1])),
	}


@frappe.whitelist()
def list_downtime_reasons() -> list[dict]:
	return frappe.get_list(
		"Downtime Reason",
		fields=["name", "title", "category", "counts_as_planned"],
		order_by="name",
		limit_page_length=MAX_LIMIT,
	)


# OEE --------------------------------------------------------------------------------------------


@frappe.whitelist()
def list_oee_periods(
	machine: str | None = None, since: str | None = None, until: str | None = None, limit: int = 100
) -> list[dict]:
	filters = []
	if machine:
		filters.append(["machine", "=", machine])
	_window(filters, "from_time", since, until)
	return frappe.get_list(
		"OEE Period",
		filters=filters,
		fields=OEE_FIELDS,
		order_by="from_time desc",
		limit_page_length=_limit(limit),
	)


# Suggestions ------------------------------------------------------------------------------------


@frappe.whitelist()
def list_suggestions(
	status: str | None = "Open",
	category: str | None = None,
	severity: str | None = None,
	agent: str | None = None,
	limit: int = 100,
) -> list[dict]:
	filters = []
	if status and status != "all":
		filters.append(["status", "=", status])
	if category:
		filters.append(["category", "=", category])
	if severity:
		filters.append(["severity", "=", severity])
	if agent:
		filters.append(["agent", "=", agent])
	return frappe.get_list(
		"Agent Suggestion",
		filters=filters,
		fields=SUGGESTION_FIELDS,
		order_by="creation desc",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def get_suggestion(name: str) -> dict:
	frappe.has_permission("Agent Suggestion", "read", name, throw=True)
	doc = frappe.get_doc("Agent Suggestion", name)
	out = {field: doc.get(field) for field in [*SUGGESTION_FIELDS, "suggestion", "resolution"]}
	evidence = doc.evidence
	if isinstance(evidence, str):
		try:
			evidence = json.loads(evidence)
		except ValueError:
			pass
	out["evidence"] = evidence
	return out


# ERP references ---------------------------------------------------------------------------------


@frappe.whitelist()
def list_erp_systems() -> dict:
	return {
		"systems": [
			{"key": adapter.key, "label": adapter.label, "available": adapter.is_available()}
			for adapter in get_adapters().values()
		],
		"default_erp_system": frappe.db.get_single_value("FoaMES Settings", "default_erp_system"),
		"reference_types": list(REFERENCE_TYPES),
	}


@frappe.whitelist()
def list_external_references(
	erp_system: str | None = None,
	reference_type: str | None = None,
	status: str | None = None,
	limit: int = 100,
) -> list[dict]:
	filters = []
	if erp_system:
		filters.append(["erp_system", "=", erp_system])
	if reference_type:
		filters.append(["reference_type", "=", reference_type])
	if status:
		filters.append(["status", "=", status])
	return frappe.get_list(
		"External Reference",
		filters=filters,
		fields=["name", "erp_system", "reference_type", "external_id", "label", "status", "last_resolved_on"],
		order_by="modified desc",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def lookup_erp_record(reference_type: str, external_id: str, erp_system: str | None = None) -> dict:
	"""Resolve one ERP record through its adapter without creating an External Reference."""
	frappe.has_permission("External Reference", "read", throw=True)
	erp_system = erp_system or frappe.db.get_single_value("FoaMES Settings", "default_erp_system")
	if not erp_system:
		frappe.throw(_("No ERP system given and no default ERP system is set in FoaMES Settings"))
	try:
		resolved = get_adapter(erp_system).resolve(reference_type, external_id)
	except AdapterError as e:
		frappe.throw(str(e))
	out = {"erp_system": erp_system, "reference_type": reference_type, "external_id": external_id}
	if not resolved:
		return {**out, "found": False}
	return {**out, "found": True, "label": resolved.label, "data": resolved.data}


# Process mining ---------------------------------------------------------------------------------


@frappe.whitelist()
def list_event_logs(status: str | None = None, limit: int = 50) -> list[dict]:
	filters = {"status": status} if status else {}
	return frappe.get_list(
		"Process Event Log",
		filters=filters,
		fields=[
			"name",
			"title",
			"status",
			"from_time",
			"to_time",
			"include_built_in",
			"event_count",
			"case_count",
			"variant_count",
			"activity_count",
			"extracted_on",
		],
		order_by="modified desc",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def list_event_log_sources() -> list[dict]:
	return frappe.get_list(
		"Event Log Source",
		fields=[
			"name",
			"enabled",
			"source_doctype",
			"case_field",
			"activity_field",
			"fixed_activity",
			"timestamp_field",
			"end_timestamp_field",
			"resource_field",
			"description",
		],
		order_by="name",
		limit_page_length=MAX_LIMIT,
	)
