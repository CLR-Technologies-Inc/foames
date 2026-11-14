# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Automatic and manual time projections over HTTP, for people, the scheduler and agents.

The arithmetic is pure, in `foames.foames_mes.cycle_time`. This module finds the Cycle Time Standard
(by name, or the machine's default), reads what the machine actually did from the same state ledger
and counter deltas OEE uses, and returns plain dicts. Nothing here writes.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime

from foames.foames_mes import cycle_time

DEFAULT_DAYS = 30
MAX_OPERATIONS = 500


def resolve_standard(standard: str | None = None, machine: str | None = None) -> str:
	"""The Cycle Time Standard to use: the one named, or the machine's enabled default."""
	if standard:
		if not frappe.db.exists("Cycle Time Standard", standard):
			frappe.throw(_("Cycle Time Standard {0} not found").format(standard), frappe.DoesNotExistError)
		return standard
	if not machine:
		frappe.throw(_("Name a standard or a machine"))
	name = frappe.db.get_value(
		"Cycle Time Standard", {"machine": machine, "is_default": 1, "disabled": 0}, "name"
	)
	if not name:
		frappe.throw(
			_("Machine {0} has no default Cycle Time Standard").format(machine), frappe.DoesNotExistError
		)
	return name


def load(name: str):
	doc = frappe.get_doc("Cycle Time Standard", name)
	doc.check_permission("read")
	return doc, doc.as_standard()


def window(since=None, until=None, days=None) -> tuple:
	until = get_datetime(until) if until else now_datetime()
	since = get_datetime(since) if since else add_to_date(until, days=-(cint(days) or DEFAULT_DAYS))
	if since >= until:
		frappe.throw(_("The window must start before it ends"))
	return since, until


def observed_for(machine: str, since, until, parts_per_cycle: float = 1.0) -> dict:
	"""Running, Idle and Setup time and parts made on a machine in [since, until), per cycle."""
	from foames.foames_mes.doctype.maintenance_plan.maintenance_plan import production
	from foames.foames_mes.doctype.oee_period.oee_period import state_intervals

	minutes = {"Running": 0.0, "Idle": 0.0, "Setup": 0.0}
	for span, state, _planned in state_intervals(machine, since, until):
		if state in minutes:
			minutes[state] += span
	parts = production(machine, since, until)
	out = cycle_time.observed(
		minutes["Running"] * 60.0, minutes["Idle"] * 60.0, minutes["Setup"] * 60.0, parts, parts_per_cycle
	)
	out.update({"machine": machine, "since": str(since), "until": str(until)})
	return out


def _projection(doc, standard, quantity, use_observed, since, until, min_cycles):
	notes, obs = [], None
	if use_observed:
		if not doc.machine:
			notes.append("the standard names no machine; using standard times")
		else:
			frappe.has_permission("Machine Event", "read", throw=True)
			obs = observed_for(doc.machine, since, until, standard.parts_per_cycle)
			standard, notes = cycle_time.calibrate(standard, obs, min_cycles)
	result = cycle_time.project(standard, quantity)
	result["notes"] = notes + result["notes"]
	result["standard"] = doc.name
	result["title"] = doc.title
	result["machine"] = doc.machine
	result["operation_reference"] = doc.operation_reference
	result["item_reference"] = doc.item_reference
	if obs is not None:
		result["observed"] = obs
	return standard, result


@frappe.whitelist(methods=["GET", "POST"])
def project_time(
	standard: str | None = None,
	machine: str | None = None,
	quantity: float = 1,
	changes: str | list | None = None,
	annual_quantity: float | None = None,
	use_observed: int = 0,
	since: str | None = None,
	until: str | None = None,
	days: int | None = None,
	min_cycles: float | None = None,
) -> dict:
	"""Elapsed, automatic and operator time for a quantity, with an optional what-if scenario.

	`changes` is a list of element changes (see `cycle_time.apply_changes`); with it the answer is
	the baseline, the scenario and their difference, and with `annual_quantity` the yearly savings.
	`use_observed` scales the automatic time to what the machine did over the window first.
	"""
	name = resolve_standard(standard, machine)
	doc, std = load(name)
	since, until = window(since, until, days) if cint(use_observed) else (None, None)
	min_cycles = flt(min_cycles) if min_cycles else cycle_time.DEFAULT_MIN_CYCLES
	base_std, baseline = _projection(doc, std, flt(quantity), cint(use_observed), since, until, min_cycles)
	changes = frappe.parse_json(changes) if isinstance(changes, str) else changes
	if not changes:
		return baseline
	scenario_std = cycle_time.apply_changes(base_std, changes)
	errors = cycle_time.problems(scenario_std)
	if errors:
		frappe.throw("<br>".join(errors), title=_("Scenario"))
	scenario = cycle_time.project(scenario_std, flt(quantity))
	scenario.update({k: baseline[k] for k in ("standard", "title", "machine")})
	scenario["changes"] = changes
	return cycle_time.compare(baseline, scenario, flt(annual_quantity) or None)


@frappe.whitelist(methods=["GET", "POST"])
def project_operations(operations: str | list, use_observed: int = 0, days: int | None = None) -> dict:
	"""Projections for many operations at once, for a scheduler.

	`operations` is a list of `{"key", "standard" or "machine", "quantity"}`; `key` is echoed back
	so the caller can match rows to its own jobs. Rows that fail carry an `error` and add nothing to
	the totals.
	"""
	operations = frappe.parse_json(operations) if isinstance(operations, str) else operations
	if not isinstance(operations, list):
		frappe.throw(_("operations must be a list"))
	if len(operations) > MAX_OPERATIONS:
		frappe.throw(_("At most {0} operations per call").format(MAX_OPERATIONS))
	since, until = window(None, None, days) if cint(use_observed) else (None, None)
	rows, totals = [], {"elapsed_minutes": 0.0, "automatic_minutes": 0.0, "operator_minutes": 0.0}
	for op in operations:
		op = op or {}
		row = {"key": op.get("key")}
		try:
			name = resolve_standard(op.get("standard"), op.get("machine"))
			doc, std = load(name)
			_std, result = _projection(
				doc,
				std,
				flt(op.get("quantity") or 0),
				cint(use_observed),
				since,
				until,
				cycle_time.DEFAULT_MIN_CYCLES,
			)
			row.update(result)
			for key in totals:
				totals[key] += result[key]
		except (frappe.ValidationError, frappe.PermissionError) as e:
			frappe.clear_last_message()
			row["error"] = str(e) or e.__class__.__name__
		rows.append(row)
	return {"operations": rows, "totals": totals}


@frappe.whitelist(methods=["GET"])
def compare_with_observed(
	standard: str | None = None,
	machine: str | None = None,
	since: str | None = None,
	until: str | None = None,
	days: int | None = None,
) -> dict:
	"""The standard's one-cycle times next to what its machine did in the window, with variances."""
	name = resolve_standard(standard, machine)
	doc, std = load(name)
	if not doc.machine:
		frappe.throw(_("Cycle Time Standard {0} names no machine").format(name))
	frappe.has_permission("Machine Event", "read", throw=True)
	since, until = window(since, until, days)
	b = cycle_time.breakdown(std).as_dict()
	obs = observed_for(doc.machine, since, until, std.parts_per_cycle)
	return {
		"standard_name": name,
		"machine": doc.machine,
		"standard": b,
		"observed": obs,
		"automatic_variance_percent": cycle_time.variance(b["automatic_seconds"], obs["automatic_seconds"]),
		"cycle_variance_percent": cycle_time.variance(b["cycle_seconds"], obs["cycle_seconds"]),
	}


@frappe.whitelist(methods=["GET"])
def get_observed_cycle(
	machine: str,
	since: str | None = None,
	until: str | None = None,
	days: int | None = None,
	parts_per_cycle: float = 1,
) -> dict:
	"""Observed automatic time and idle time per cycle on a machine, without a standard."""
	frappe.has_permission("Machine Event", "read", throw=True)
	if not frappe.db.exists("Machine", machine):
		frappe.throw(_("Machine {0} not found").format(machine), frappe.DoesNotExistError)
	since, until = window(since, until, days)
	return observed_for(machine, since, until, flt(parts_per_cycle) or 1.0)
