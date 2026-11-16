# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The floor snapshot: one plain dict describing the plant right now.

The visual floor page renders it, the built-in rules read it, and external agents fetch it
through the API. Everything an agent needs to reason about the floor is in here, so an agent
never has to query DocTypes one by one.

Other apps add their own sections through the `foames_floor_snapshot_extensions` hook: each
dotted path is called with the snapshot dict, the start of the window and the current time, and
adds keys to the dict in place.

A snapshot read for a person or an agent (`for_user=True`, as the API, the Floor View page and the
MCP tool read it) holds only what that reader may see: the machines their role and user permissions
allow, the sections of DocTypes they may read, and no row about another machine. Extensions find the
reader's machines in `snapshot["scope"]["machines"]` (None for a system read) and must keep to them;
whatever they add is scrubbed of other machines afterwards all the same. The snapshot is built fresh
on every call and never cached, so one reader's scope cannot reach another.
"""

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, get_datetime, now_datetime

from foames.foames_kernel import record_scope
from foames.foames_mes.counters import minutes_between
from foames.foames_mes.doctype.andon_call.andon_call import open_andon_calls
from foames.foames_mes.doctype.recognition.recognition import floor_recognitions
from foames.foames_mes.doctype.shift_pattern.shift_pattern import load_pattern
from foames.foames_mes.doctype.work_instruction_run.work_instruction_run import active_runs
from foames.foames_mes.shifts import window_at

MACHINE_FIELDS = [
	"name",
	"title",
	"status",
	"last_seen",
	"last_count_at",
	"machine_type",
	"ecl",
	"ideal_cycle_seconds",
	"current_job_reference",
	"current_job_since",
	"shift_pattern",
]
SUGGESTION_FIELDS = ["name", "title", "category", "severity", "agent", "reference_doctype", "reference_name"]


def _reader(for_user: bool):
	"""(list function, may-read check) for a system read or a read on behalf of the session user."""
	if not for_user:
		return frappe.get_all, lambda doctype: True

	def list_for_user(doctype, **kwargs):
		kwargs.setdefault("limit_page_length", 0)
		return frappe.get_list(doctype, **kwargs)

	return list_for_user, lambda doctype: bool(frappe.has_permission(doctype, "read"))


def floor_snapshot(days: int = 1, for_user: bool = False) -> dict:
	"""The plant now. A system read (the scheduler's rules) sees every machine; `for_user=True`
	scopes it to what the session user may read."""
	now = now_datetime()
	since = add_days(now, -days)
	list_of, may_read = _reader(for_user)
	machines = list_of("Machine", filters={"disabled": 0}, fields=MACHINE_FIELDS, order_by="name")
	allowed = {m.name for m in machines} if for_user else None
	jobs = (
		current_jobs([m.current_job_reference for m in machines if m.current_job_reference], list_of)
		if may_read("External Reference")
		else {}
	)
	andon = record_scope.filter_rows(open_andon_calls(now), allowed) if may_read("Andon Call") else []
	runs = record_scope.filter_rows(active_runs(now), allowed) if may_read("Work Instruction Run") else []
	read_counts = may_read("Machine Event")
	read_oee = may_read("OEE Period")
	for m in machines:
		reference = m.pop("current_job_reference")
		# A reader who may not read External References still sees that a job is set, which the
		# Machine record itself shows, but not the ERP record behind it.
		m["current_job"] = jobs.get(reference) or ({"reference": reference} if reference else None)
		if m["current_job"]:
			m["current_job"]["since"] = m.current_job_since
		m.pop("current_job_since")
		m["shift"] = current_shift(m.pop("shift_pattern"), now)
		m["ecl"] = int(m.ecl) if m.ecl else None
		m["andon"] = [c for c in andon if c.machine == m.name]
		m["work_instruction_runs"] = [r for r in runs if r.machine == m.name]
		# Measured from the machine's latest count ever (kept on the Machine by event processing), not
		# only inside the window, so a machine that counted yesterday and reports Running without
		# counting today is still caught by the rules.
		last_count_at = m.pop("last_count_at")
		m["minutes_since_count"] = (
			minutes_between(get_datetime(last_count_at), now) if last_count_at else None
		)
		m["counts"] = counts_since(m.name, since) if read_counts else {}
		m["oee_today"] = latest_oee(m.name, list_of) if read_oee else None
	downtime = []
	period = f"{since:%Y-%m-%d} to {now:%Y-%m-%d}"
	for m in machines if may_read("Downtime Record") else []:
		by_reason = downtime_by_reason(m.name, since, now, ignore_permissions=not for_user)
		classified = {reason: minutes for reason, minutes in by_reason.items() if reason}
		if classified:
			top_reason, top_minutes = max(classified.items(), key=lambda item: item[1])
			downtime.append(
				{
					"machine": m.name,
					"period": period,
					"total_minutes": sum(by_reason.values()),
					"unclassified_minutes": by_reason.get(None, 0),
					"top_reason": top_reason,
					"top_minutes": top_minutes,
				}
			)
	references = (
		list_of(
			"External Reference",
			filters={"status": "Missing"},
			fields=["name", "reference_type", "external_id", "status"],
		)
		if may_read("External Reference")
		else []
	)
	suggestions = (
		record_scope.filter_rows(
			list_of("Agent Suggestion", filters={"status": "Open"}, fields=SUGGESTION_FIELDS), allowed
		)
		if may_read("Agent Suggestion")
		else []
	)
	snapshot = {
		"as_of": now,
		"scope": {
			"user": frappe.session.user if for_user else None,
			"machines": sorted(allowed) if for_user else None,
		},
		"machines": machines,
		"downtime_by_machine": downtime,
		"external_references": references,
		"andon_calls": andon,
		# Recent thanks to people and teams. Private ones and people who opted out never appear.
		"recognitions": record_scope.filter_rows(floor_recognitions(now), allowed)
		if frappe.has_permission("Recognition", "read")
		else [],
		"work_instruction_runs": runs,
		"open_suggestions": suggestions,
	}
	for extension in frappe.get_hooks("foames_floor_snapshot_extensions") or []:
		frappe.get_attr(extension)(snapshot, since, now)
	return record_scope.scrub(snapshot, allowed) if for_user else snapshot


def latest_oee(machine: str, list_of=frappe.get_all) -> dict | None:
	"""The machine's latest OEE Period: oee, availability, performance and quality."""
	rows = list_of(
		"OEE Period",
		filters={"machine": machine},
		fields=["oee", "availability", "performance", "quality"],
		order_by="from_time desc",
		limit_page_length=1,
	)
	return rows[0] if rows else None


def current_shift(pattern: str | None, now) -> dict | None:
	"""{name, start, end} of the pattern's shift running at `now`, or None when the machine has no
	pattern or is off shift."""
	if not pattern:
		return None
	shifts, holidays = load_pattern(pattern)
	window = window_at(now, shifts, holidays)
	if not window:
		return None
	return {"name": window.shift, "start": window.start, "end": window.end}


def current_jobs(references: list[str], list_of=frappe.get_all) -> dict[str, dict]:
	"""External Reference name -> {reference, erp_system, external_id, label, status} for the jobs
	machines are working on."""
	if not references:
		return {}
	return {
		r.name: {
			"reference": r.name,
			"erp_system": r.erp_system,
			"external_id": r.external_id,
			"label": r.label,
			"status": r.status,
		}
		for r in list_of(
			"External Reference",
			filters={"name": ("in", references)},
			fields=["name", "erp_system", "external_id", "label", "status"],
		)
	}


def downtime_by_reason(
	machine: str, since, until, ignore_permissions: bool = True
) -> dict[str | None, float]:
	"""Minutes of downtime per reason inside [since, until), counting the part of each record that
	overlaps the window. Open downtime counts up to `until`. Downtime with no reason assigned yet is
	returned under the key None, so shares are computed over all downtime, not only the classified part.

	The snapshot and the rules read every record. A read on behalf of a user (the MCP tools) passes
	`ignore_permissions=False`, so that user's role and user permissions filter the records."""
	rows = frappe.get_list(
		"Downtime Record",
		filters=[
			["machine", "=", machine],
			["start_time", "<", until],
		],
		or_filters=[["end_time", "is", "not set"], ["end_time", ">=", since]],
		fields=["reason", "start_time", "end_time"],
		ignore_permissions=ignore_permissions,
	)
	minutes: dict[str, float] = {}
	for r in rows:
		start = max(get_datetime(r.start_time), since)
		end = min(get_datetime(r.end_time), until) if r.end_time else until
		if end > start:
			minutes[r.reason] = minutes.get(r.reason, 0) + minutes_between(start, end)
	return minutes


def counts_since(machine: str, since) -> dict[str, float]:
	"""Counter deltas per counter name since `since`, for example {"good": 120, "scrap": 3}."""
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.counter_name, Sum(event.delta).as_("total"))
		.where((event.machine == machine) & (event.event_type == "Count") & (event.timestamp >= since))
		.groupby(event.counter_name)
		.run(as_dict=True)
	)
	return {r.counter_name: r.total or 0 for r in rows}


def collect_findings(snapshot: dict) -> list[dict]:
	"""The built-in rules plus every rule registered through the `foames_suggestion_rules` hook."""
	from foames.foames_mes.suggestions import all_rules
	from foames.foames_mes.work_instructions import stalled_runs

	findings = all_rules(snapshot)
	findings.extend(stalled_runs(snapshot))
	findings.extend(_spc_findings())
	for rule in frappe.get_hooks("foames_suggestion_rules") or []:
		findings.extend(frappe.get_attr(rule)(snapshot))
	return findings


def _spc_findings() -> list[dict]:
	"""Control chart signals on recent Measurement events; a failure here never stops the other rules."""
	from foames.foames_mes.spc_monitor import spc_findings

	try:
		return spc_findings()
	except Exception:
		frappe.log_error(title="FoaMES SPC rules", message=frappe.get_traceback())
		return []
