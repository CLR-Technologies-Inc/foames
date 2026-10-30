# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OEE for one machine over one period, computed from its Machine Events and Downtime Records."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_to_date, get_datetime, getdate, now_datetime

from foames.foames_mes.counters import minutes_between
from foames.foames_mes.oee import compute_oee, ledger_from_states


class OEEPeriod(Document):
	def validate(self):
		if get_datetime(self.to_time) <= get_datetime(self.from_time):
			frappe.throw(_("The period must end after it starts"))
		if not self.planned_minutes or self.planned_minutes <= 0:
			frappe.throw(_("Planned minutes must be positive"))
		self.compute()

	def compute(self):
		start, end = get_datetime(self.from_time), get_datetime(self.to_time)
		machine = frappe.get_cached_doc("Machine", self.machine)
		self.ideal_cycle_seconds = self.ideal_cycle_seconds or machine.ideal_cycle_seconds
		intervals = state_intervals(self.machine, start, end)
		ledger = ledger_from_states(intervals, self.planned_minutes)
		good, scrap = counts_in(self.machine, start, end)
		result = compute_oee(ledger, good, scrap, self.ideal_cycle_seconds)
		self.run_minutes = ledger.run_minutes
		self.planned_downtime_minutes = ledger.planned_downtime_minutes
		self.unplanned_downtime_minutes = ledger.unplanned_downtime_minutes
		self.unknown_minutes = ledger.unknown_minutes
		self.coverage = ledger.coverage * 100
		self.good_count, self.scrap_count = good, scrap
		self.availability = result.availability * 100
		self.performance = result.performance * 100
		self.quality = result.quality * 100
		self.oee = result.oee * 100
		self.flags.notes = result.notes


def state_intervals(machine: str, start, end) -> list[tuple[float, str, bool]]:
	"""(minutes, state, planned) for the machine's state history inside [start, end).

	The state before `start` carries into the period. Down intervals take their planned flag from
	the Downtime Record's reason, when one is assigned.
	"""
	state_filters = {"machine": machine, "event_type": ("in", ("State", "Alarm"))}
	before = frappe.get_all(
		"Machine Event",
		filters={**state_filters, "timestamp": ("<=", start)},
		fields=["timestamp", "state", "event_type"],
		order_by="timestamp desc, creation desc",
		limit_page_length=1,
	)
	events = before + frappe.get_all(
		"Machine Event",
		filters=[
			["machine", "=", machine],
			["event_type", "in", ("State", "Alarm")],
			["timestamp", ">", start],
			["timestamp", "<", end],
		],
		fields=["timestamp", "state", "event_type"],
		order_by="timestamp asc",
	)
	planned_windows = [
		(get_datetime(d.start_time), get_datetime(d.end_time) if d.end_time else end)
		for d in frappe.get_all(
			"Downtime Record",
			filters={"machine": machine, "start_time": ("<", end), "reason": ("is", "set")},
			or_filters=[["end_time", "is", "not set"], ["end_time", ">=", start]],
			fields=["start_time", "end_time", "reason"],
		)
		if frappe.db.get_value("Downtime Reason", d.reason, "counts_as_planned")
	]
	state, cursor = "Unknown", start
	for e in events:
		at = get_datetime(e.timestamp)
		new_state = "Down" if e.event_type == "Alarm" else e.state
		if at <= start:
			state = new_state
			continue
		yield_from = cursor
		cursor = at
		intervals_append = (minutes_between(yield_from, at), state, _is_planned(yield_from, planned_windows))
		state = new_state
		yield intervals_append
	if cursor < end:
		yield (minutes_between(cursor, end), state, _is_planned(cursor, planned_windows))


def _is_planned(at, windows) -> bool:
	return any(s <= at < e for s, e in windows)


def counts_in(machine: str, start, end) -> tuple[float, float]:
	rows = frappe.get_all(
		"Machine Event",
		filters=[
			["machine", "=", machine],
			["event_type", "=", "Count"],
			["timestamp", ">=", start],
			["timestamp", "<", end],
		],
		fields=["counter_name", "sum(delta) as total"],
		group_by="counter_name",
	)
	good = sum(r.total or 0 for r in rows if r.counter_name in ("good", "count", "total", "parts"))
	scrap = sum(r.total or 0 for r in rows if r.counter_name in ("scrap", "reject", "bad", "ng"))
	return good, scrap


def compute_daily_oee(for_date=None):
	"""Scheduled daily: one OEE Period per enabled machine for the previous day.

	A machine with a Shift Start is measured over its scheduled window only, so state time and counts
	outside the shift never enter the period. Without one, the whole day is the planned time.
	"""
	day = getdate(for_date) if for_date else add_days(getdate(now_datetime()), -1)
	created = []
	for m in frappe.get_all("Machine", {"disabled": 0}, ["name", "scheduled_minutes_per_day", "shift_start"]):
		start, end, planned = scheduled_window(day, m.shift_start, m.scheduled_minutes_per_day)
		if frappe.db.exists("OEE Period", {"machine": m.name, "from_time": start, "to_time": end}):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "OEE Period",
				"machine": m.name,
				"from_time": start,
				"to_time": end,
				"planned_minutes": planned,
			}
		).insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def scheduled_window(day, shift_start, scheduled_minutes):
	"""(from, to, planned minutes) of a machine's production window on `day`."""
	if shift_start and scheduled_minutes and scheduled_minutes > 0:
		start = get_datetime(f"{day} {shift_start}")
		return start, add_to_date(start, minutes=scheduled_minutes), scheduled_minutes
	start = get_datetime(f"{day} 00:00:00")
	return start, get_datetime(f"{add_days(day, 1)} 00:00:00"), 1440


@frappe.whitelist()
def get_oee(machine: str, from_time, to_time, planned_minutes: float | None = None) -> dict:
	"""OEE on demand, without saving a period."""
	frappe.has_permission("OEE Period", "read", throw=True)
	start, end = get_datetime(from_time), get_datetime(to_time)
	doc = frappe.get_doc(
		{
			"doctype": "OEE Period",
			"machine": machine,
			"from_time": start,
			"to_time": end,
			"planned_minutes": planned_minutes or minutes_between(start, end),
		}
	)
	doc.validate()
	out = {
		k: doc.get(k)
		for k in (
			"availability",
			"performance",
			"quality",
			"oee",
			"run_minutes",
			"unknown_minutes",
			"coverage",
			"good_count",
			"scrap_count",
		)
	}
	out["notes"] = doc.flags.notes
	return out
