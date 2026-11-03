# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A preventive maintenance task for one machine, due by calendar, run hours or counts.

The meter is read from data FoaMES already keeps: Running time from the OEE state ledger (Downtime
Records overlaid, Unknown never counted) and production from the stored counter deltas. Nothing is
inferred from missing events, so a machine that stops reporting stops wearing on paper too.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Sum
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes.counters import GOOD_COUNTERS, SCRAP_COUNTERS
from foames.foames_mes.maintenance import assess, calendar_days, projected_due

OPEN_WORK_ORDER_STATUSES = ("Open", "In Progress")


class MaintenancePlan(Document):
	def validate(self):
		if not self.interval or self.interval <= 0:
			frappe.throw(_("The interval must be positive"))
		if self.warn_percent is None or self.warn_percent == "":
			self.warn_percent = 90
		if not 0 < float(self.warn_percent) <= 100:
			frappe.throw(_("Due Soon At must be between 0 and 100 percent"))
		if self.grace_percent is None or float(self.grace_percent) < 0:
			self.grace_percent = 10
		if self.trigger_type != "Count":
			self.counter_name = None
		elif self.counter_name:
			# Machine Events store counter names in lower case.
			self.counter_name = self.counter_name.strip().lower()
		now = now_datetime()
		if not self.last_done_on:
			self.last_done_on = now
		elif get_datetime(self.last_done_on) > now:
			frappe.throw(_("The last service cannot be in the future"))
		self.apply_meter(self.measure(now))

	def measure(self, now=None) -> dict:
		"""The plan's meter at `now`: used, percent, remaining, status, due_on and the open work order."""
		now = get_datetime(now) if now else now_datetime()
		since = get_datetime(self.last_done_on) if self.last_done_on else now
		used = meter_reading(self.trigger_type, self.machine, since, now, self.counter_name)
		result = assess(used, self.interval, self.warn_percent, self.grace_percent)
		result.update(
			{
				"used": used,
				"since": since,
				"checked": now,
				"due_on": projected_due(used, self.interval, since, now, self.trigger_type),
				"open_work_order": open_work_order(self.name) if self.name and not self.is_new() else None,
			}
		)
		return result

	def apply_meter(self, meter: dict):
		for field, value in meter_fields(meter).items():
			self.set(field, value)


def meter_fields(meter: dict) -> dict:
	return {
		"used": meter["used"],
		"percent_used": meter["percent"],
		"remaining": meter["remaining"],
		"status": meter["status"],
		"due_on": meter["due_on"],
		"open_work_order": meter["open_work_order"],
		"last_checked": meter["checked"],
	}


def meter_reading(trigger: str, machine: str, since, until, counter_name: str | None = None) -> float:
	if trigger == "Calendar":
		return calendar_days(since, until)
	if trigger == "Run Hours":
		return run_hours(machine, since, until)
	if trigger == "Count":
		return production(machine, since, until, counter_name)
	frappe.throw(_("Unknown trigger {0}").format(trigger))


def run_hours(machine: str, since, until) -> float:
	"""Running hours in [since, until), from the same state ledger as OEE."""
	from foames.foames_mes.doctype.oee_period.oee_period import state_intervals

	if until <= since:
		return 0.0
	return (
		sum(
			minutes
			for minutes, state, _planned in state_intervals(machine, since, until)
			if state == "Running"
		)
		/ 60.0
	)


def production(machine: str, since, until, counter_name: str | None = None) -> float:
	"""Counter deltas in [since, until): one named counter, or good plus scrap."""
	names = [counter_name] if counter_name else list(GOOD_COUNTERS + SCRAP_COUNTERS)
	event = frappe.qb.DocType("Machine Event")
	rows = (
		frappe.qb.from_(event)
		.select(Sum(event.delta).as_("total"))
		.where(
			(event.machine == machine)
			& (event.event_type == "Count")
			& (event.counter_name.isin(names))
			& (event.timestamp >= since)
			& (event.timestamp < until)
		)
		.run(as_dict=True)
	)
	return float((rows[0].total if rows else 0) or 0)


def open_work_order(plan: str) -> str | None:
	return frappe.db.get_value(
		"Maintenance Work Order",
		{"maintenance_plan": plan, "status": ("in", OPEN_WORK_ORDER_STATUSES)},
		"name",
		order_by="creation asc",
	)


def refresh_plan(name: str, now=None) -> tuple:
	"""Read one plan's meter and store it without touching the plan's Modified. Returns (doc, meter)."""
	doc = frappe.get_doc("Maintenance Plan", name)
	meter = doc.measure(now)
	frappe.db.set_value("Maintenance Plan", name, meter_fields(meter), update_modified=False)
	doc.apply_meter(meter)
	return doc, meter


def create_work_order(plan, meter: dict | None = None) -> str:
	"""A Maintenance Work Order for the plan, or the one already open."""
	plan = plan if not isinstance(plan, str) else frappe.get_doc("Maintenance Plan", plan)
	existing = open_work_order(plan.name)
	if existing:
		return existing
	meter = meter or plan.measure()
	doc = frappe.get_doc(
		{
			"doctype": "Maintenance Work Order",
			"maintenance_plan": plan.name,
			"due_on": meter.get("due_on"),
		}
	).insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def make_work_order(plan: str) -> str:
	"""The form button: open a work order for the plan now (or return the open one)."""
	frappe.has_permission("Maintenance Work Order", "create", throw=True)
	frappe.has_permission("Maintenance Plan", "read", doc=plan, throw=True)
	return create_work_order(plan)


def check_maintenance_plans(now=None) -> list[str]:
	"""Scheduled hourly: read every enabled plan's meter, open work orders where the plan asks for it,
	and raise an Agent Suggestion for each plan that is Due Soon, Due or Overdue. Returns the
	suggestions created or reopened."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
	from foames.foames_mes.maintenance import findings

	rows = []
	for name in frappe.get_all("Maintenance Plan", filters={"disabled": 0}, pluck="name", order_by="name"):
		plan, meter = refresh_plan(name, now)
		if (
			meter["status"] in ("Due", "Overdue")
			and plan.auto_create_work_order
			and not meter["open_work_order"]
		):
			meter["open_work_order"] = create_work_order(plan, meter)
			frappe.db.set_value(
				"Maintenance Plan", name, "open_work_order", meter["open_work_order"], update_modified=False
			)
		rows.append(
			{
				"name": name,
				"title": plan.title,
				"machine": plan.machine,
				"trigger": plan.trigger_type,
				"interval": plan.interval,
				"used": meter["used"],
				"percent": meter["percent"],
				"status": meter["status"],
				"since": meter["since"],
				"due_on": meter["due_on"],
				"open_work_order": meter["open_work_order"],
			}
		)
	return raise_suggestions(findings(rows), agent="foames-maintenance")
