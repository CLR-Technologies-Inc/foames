# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A finite-capacity production schedule.

The rows hold the operations to plan. **Build** reads each machine's working windows (its Shift
Pattern, or its daily window), takes out maintenance and planned stops, works out setup and run
minutes per eligible machine, runs the pure scheduler in `foames.foames_mes.scheduling` and writes
one Scheduled Operation per row. **Publish** makes it the schedule the floor follows and
supersedes the one published before it for the same line.

Rows come from people, from an import, or from the demand sources other apps and the adapters
register under the `foames_schedule_demand_sources` hook (**Get Operations**). Cycle times come from
the row, from the `foames_cycle_time_estimators` hook, or from the machine's Ideal Cycle Seconds.
Nothing here writes to an ERP or to a machine.
"""

import json
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_to_date, cint, flt, get_datetime, now_datetime

from foames.foames_mes.doctype.oee_period.oee_period import operating_windows
from foames.foames_mes.scheduling import (
	Operation,
	behind_schedule_findings,
	current_and_next,
	subtract,
)
from foames.foames_mes.scheduling import schedule as run_scheduler

MAX_HORIZON_DAYS = 90
MACHINE_FIELDS = (
	"name",
	"title",
	"line",
	"machine_type",
	"ideal_cycle_seconds",
	"shift_pattern",
	"shift_start",
	"scheduled_minutes_per_day",
	"current_job_reference",
)


class ProductionSchedule(Document):
	def validate(self):
		if not self.title and self.schedule_start:
			self.title = _("Schedule from {0}").format(
				get_datetime(self.schedule_start).strftime("%Y-%m-%d %H:%M")
			)
		if cint(self.horizon_days) < 1 or cint(self.horizon_days) > MAX_HORIZON_DAYS:
			frappe.throw(_("Horizon Days must be between 1 and {0}").format(MAX_HORIZON_DAYS))
		known = set(frappe.get_all("Machine", pluck="name"))
		for row in self.jobs:
			unknown = [m for m in split_machines(row.machines) if m not in known]
			if unknown:
				frappe.throw(_("Row {0}: unknown machine {1}").format(row.idx, ", ".join(unknown)))
			for fieldname in (
				"quantity",
				"setup_minutes",
				"run_minutes",
				"cycle_seconds",
				"transfer_minutes",
			):
				if flt(row.get(fieldname)) < 0:
					frappe.throw(
						_("Row {0}: {1} cannot be negative").format(row.idx, row.meta.get_label(fieldname))
					)
			row.source = row.source or "Manual"

	def on_trash(self):
		frappe.db.delete("Scheduled Operation", {"production_schedule": self.name})

	@property
	def horizon_end(self):
		return add_days(get_datetime(self.schedule_start), cint(self.horizon_days))

	@frappe.whitelist()
	def build(self):
		"""Plan the rows and replace this schedule's Scheduled Operations."""
		self.check_permission("write")
		if self.status != "Draft":
			frappe.throw(_("Only a draft schedule can be rebuilt; copy it to plan again"))
		result, problems = self.plan()
		frappe.db.delete("Scheduled Operation", {"production_schedule": self.name})
		rows = {row.name: row for row in self.jobs}
		for slot in result.slots:
			row = rows[slot.key]
			late = slot.lateness_minutes
			self.insert_operation(
				row,
				machine=slot.machine,
				start_time=slot.start,
				end_time=slot.end,
				setup_minutes=slot.setup_minutes,
				run_minutes=slot.run_minutes,
				setup_skipped=int(slot.setup_skipped),
				split=int(slot.split),
				lateness_minutes=late,
				status="Late" if late is not None and late > 0 else "Scheduled",
			)
		for missing in result.unscheduled:
			row = rows[missing.key]
			self.insert_operation(row, status="Unscheduled", reason=missing.reason)
		k = result.kpis
		self.operations_scheduled = k["scheduled"]
		self.operations_unscheduled = k["unscheduled"]
		self.late_jobs = len(k["late_jobs"])
		self.total_tardiness_minutes = k["total_tardiness_minutes"]
		self.makespan_end = k["makespan_end"]
		self.machine_load = json.dumps(k["machine_load"], indent=1, sort_keys=True)
		self.problems = "\n".join(problems) or None
		self.built_on = now_datetime()
		self.save()
		return {**{key: value for key, value in k.items() if key != "machine_load"}, "problems": problems}

	def insert_operation(self, row, **values):
		label = row.operation or _("Operation {0}").format(row.sequence)
		frappe.get_doc(
			{
				"doctype": "Scheduled Operation",
				"production_schedule": self.name,
				"title": f"{row.job}: {label}",
				"job": row.job,
				"operation": row.operation,
				"sequence": row.sequence,
				"due_date": row.due_date,
				"job_reference": row.job_reference,
				**values,
			}
		).insert(ignore_permissions=True)

	def plan(self):
		"""Run the scheduler over the rows without saving anything. Returns (result, problems)."""
		start, end = get_datetime(self.schedule_start), self.horizon_end
		machines = scope_machines(self.line)
		by_name = {m.name: m for m in machines}
		calendars = {m.name: calendar(m, start, end) for m in machines}
		running = {m.current_job_reference: m.name for m in machines if m.current_job_reference}
		problems = []
		operations = []
		for order, row in enumerate(self.jobs):
			eligible = eligible_machines(row, machines)
			pinned = running.get(row.job_reference) if row.job_reference else None
			if pinned and pinned not in eligible:
				eligible.append(pinned)
			times = {}
			for name in eligible:
				minutes = operation_minutes(row, by_name[name])
				if minutes is None:
					problems.append(_("Row {0} ({1}): no cycle time on {2}").format(row.idx, row.job, name))
					continue
				times[name] = minutes
			label = f"{row.job} {row.operation or row.sequence}"
			operations.append(
				Operation(
					key=row.name,
					job=row.job,
					sequence=cint(row.sequence),
					machines=times,
					due=get_datetime(row.due_date) if row.due_date else None,
					release=get_datetime(row.release_date) if row.release_date else None,
					priority=cint(row.priority),
					setup_group=row.setup_group or None,
					transfer_minutes=flt(row.transfer_minutes),
					pinned_machine=pinned if pinned in times else None,
					order=order,
					label=label,
				)
			)
		result = run_scheduler(
			operations, calendars, start, end, rule=self.dispatch_rule or "EDD", split=bool(self.allow_split)
		)
		return result, problems

	@frappe.whitelist()
	def get_operations(self, replace: int = 1):
		"""Fill the rows from every registered demand source. With `replace`, rows that came from a
		source are dropped first; rows typed in by hand stay."""
		self.check_permission("write")
		if self.status != "Draft":
			frappe.throw(_("Only a draft schedule takes new operations"))
		found = []
		for path in frappe.get_hooks("foames_schedule_demand_sources") or []:
			found.extend(frappe.get_attr(path)(self.schedule_start, self.horizon_end, self.line) or [])
		if cint(replace):
			self.set("jobs", [row for row in self.jobs if (row.source or "Manual") == "Manual"])
		for values in found:
			self.append("jobs", values)
		self.save()
		return len(found)

	@frappe.whitelist()
	def publish(self):
		"""Make this the schedule the floor follows; the one published before it for the same line
		is superseded."""
		self.check_permission("write")
		if self.status != "Draft":
			frappe.throw(_("Only a draft schedule can be published"))
		if not self.built_on:
			frappe.throw(_("Build the schedule before publishing it"))
		for name in frappe.get_all(
			"Production Schedule",
			filters={
				"status": "Published",
				"line": self.line or ("is", "not set"),
				"name": ("!=", self.name),
			},
			pluck="name",
		):
			frappe.db.set_value("Production Schedule", name, "status", "Superseded")
		self.status = "Published"
		self.published_on = now_datetime()
		self.published_by = frappe.session.user
		self.save()

	@frappe.whitelist()
	def copy_to_draft(self):
		"""A new draft with the same rows and settings, starting now, to plan again."""
		frappe.has_permission("Production Schedule", "create", throw=True)
		new = frappe.copy_doc(self)
		new.status = "Draft"
		new.schedule_start = now_datetime()
		new.title = None
		for fieldname in (
			"operations_scheduled",
			"operations_unscheduled",
			"late_jobs",
			"total_tardiness_minutes",
			"makespan_end",
			"built_on",
			"published_on",
			"published_by",
			"machine_load",
			"problems",
		):
			new.set(fieldname, None)
		new.insert()
		return new.name


def split_machines(value) -> list[str]:
	return [m.strip() for m in re.split(r"[,\n]", value or "") if m.strip()]


def scope_machines(line: str | None = None) -> list:
	filters = {"disabled": 0}
	if line:
		filters["line"] = line
	return frappe.get_all("Machine", filters=filters, fields=list(MACHINE_FIELDS), order_by="name")


def eligible_machines(row, machines) -> list[str]:
	"""The machines a row may run on, within the schedule's scope."""
	listed = split_machines(row.machines)
	if listed:
		names = {m.name for m in machines}
		return [m for m in listed if m in names]
	if row.machine_type:
		return [m.name for m in machines if m.machine_type == row.machine_type]
	return [m.name for m in machines]


def calendar(machine, start, end) -> list[tuple]:
	"""A machine's working windows in [start, end) without its maintenance and planned stops."""
	windows = operating_windows(machine, start, end)
	return subtract(windows, blocked_time(machine.name, start, end))


def blocked_time(machine: str, start, end) -> list[tuple]:
	"""Time a machine cannot run work: open Maintenance Work Orders (from their start, or their due
	time, for the plan's estimated minutes) and Downtime Records entered ahead with both ends."""
	blocks = []
	orders = frappe.get_all(
		"Maintenance Work Order",
		filters={"machine": machine, "status": ("in", ("Open", "In Progress"))},
		fields=["maintenance_plan", "status", "started_on", "due_on"],
	)
	for wo in orders:
		minutes = flt(frappe.db.get_value("Maintenance Plan", wo.maintenance_plan, "estimated_minutes"))
		begin = wo.started_on if wo.status == "In Progress" and wo.started_on else wo.due_on
		if not begin or minutes <= 0:
			continue
		begin = get_datetime(begin)
		finish = add_to_date(begin, minutes=minutes)
		if wo.status == "In Progress":
			# Work under way blocks the machine at least until the schedule starts.
			finish = max(finish, get_datetime(start))
		blocks.append((begin, finish))
	planned = frappe.qb.DocType("Downtime Record")
	rows = (
		frappe.qb.from_(planned)
		.select(planned.start_time, planned.end_time)
		.where(planned.machine == machine)
		.where(planned.end_time.isnotnull())
		.where(planned.end_time > get_datetime(start))
		.where(planned.start_time < get_datetime(end))
		.run(as_dict=True)
	)
	blocks.extend((get_datetime(r.start_time), get_datetime(r.end_time)) for r in rows)
	return blocks


def operation_minutes(row, machine) -> tuple[float, float] | None:
	"""(setup, run) minutes of a row on a machine, or None when no cycle time is known.

	The run time is the row's Run Minutes; else its quantity times a cycle time taken, in order, from
	the row, from the first `foames_cycle_time_estimators` hook that answers, and from the machine's
	Ideal Cycle Seconds."""
	setup = flt(row.setup_minutes)
	if row.run_minutes:
		return setup, flt(row.run_minutes)
	quantity = flt(row.quantity)
	if quantity <= 0:
		return setup, 0.0
	seconds = (
		flt(row.cycle_seconds) or estimated_cycle_seconds(row, machine) or flt(machine.ideal_cycle_seconds)
	)
	if not seconds:
		return None
	return setup, quantity * seconds / 60.0


def estimated_cycle_seconds(row, machine) -> float | None:
	"""Seconds per unit from the `foames_cycle_time_estimators` hooks: each is called with the row
	as a dict and the machine row, and returns a positive number or None."""
	for path in frappe.get_hooks("foames_cycle_time_estimators") or []:
		value = frappe.get_attr(path)(row.as_dict(), machine)
		if value and flt(value) > 0:
			return flt(value)
	return None


# The floor


def published_slots(machines: list[str], since, until) -> dict[str, list[dict]]:
	"""Scheduled operations of published schedules that overlap [since, until), by machine."""
	if not machines:
		return {}
	published = frappe.get_all("Production Schedule", filters={"status": "Published"}, pluck="name")
	if not published:
		return {}
	op = frappe.qb.DocType("Scheduled Operation")
	rows = (
		frappe.qb.from_(op)
		.select(
			op.name,
			op.production_schedule,
			op.machine,
			op.job,
			op.operation,
			op.start_time,
			op.end_time,
			op.status,
			op.job_reference,
		)
		.where(op.production_schedule.isin(published))
		.where(op.machine.isin(machines))
		.where(op.end_time > since)
		.where(op.start_time < until)
		.orderby(op.start_time)
		.run(as_dict=True)
	)
	out: dict[str, list[dict]] = {}
	for r in rows:
		out.setdefault(r.machine, []).append(
			{
				"name": r.name,
				"production_schedule": r.production_schedule,
				"job": r.job,
				"operation": r.operation,
				"start": get_datetime(r.start_time),
				"end": get_datetime(r.end_time),
				"status": r.status,
				"job_reference": r.job_reference,
			}
		)
	return out


def extend_snapshot(snapshot: dict, since, now):
	"""Registered under `foames_floor_snapshot_extensions`: each machine gets `schedule`, the
	operation the published schedule has it on now and the next three."""
	if not frappe.has_permission("Scheduled Operation", "read"):
		return
	names = [m["name"] for m in snapshot.get("machines", [])]
	slots = published_slots(names, now, add_days(now, 7))
	for m in snapshot.get("machines", []):
		m["schedule"] = current_and_next(slots.get(m["name"], []), get_datetime(now))


def behind_schedule(snapshot: dict) -> list[dict]:
	"""Registered under `foames_suggestion_rules`: a machine that should be running a scheduled
	operation but reports Down, Idle, Setup or Unknown."""
	machines = [m for m in snapshot.get("machines", []) if m.get("schedule")]
	if not machines:
		return []
	return behind_schedule_findings(machines, now_datetime())


@frappe.whitelist()
def get_machine_schedule(machine: str | None = None, days: int = 1) -> list[dict]:
	"""The published operations from now for `days` days, for one machine or all of them."""
	frappe.has_permission("Scheduled Operation", "read", throw=True)
	now = now_datetime()
	names = [machine] if machine else frappe.get_all("Machine", filters={"disabled": 0}, pluck="name")
	slots = published_slots(names, now, add_days(now, max(cint(days), 1)))
	out = [dict(s, machine=m) for m, rows in slots.items() for s in rows]
	return sorted(out, key=lambda s: (s["start"], s["machine"]))
