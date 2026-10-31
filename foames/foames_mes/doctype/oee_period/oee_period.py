# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OEE for one machine over one period, computed from its Machine Events and Downtime Records."""

from itertools import pairwise

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_to_date, get_datetime, getdate, now_datetime

from foames.foames_mes.counters import good_and_scrap, minutes_between
from foames.foames_mes.events import counter_totals
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

	The state before `start` carries into the period. Every Downtime Record that overlaps the period
	makes its minutes Down, whatever the state events say, so a stoppage an operator recorded by
	hand counts even when the machine never reported it. A Down minute is planned when a record
	covering it has a reason that counts as planned downtime.
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
	windows = downtime_windows(machine, start, end)
	state, changes = "Unknown", []
	for e in events:
		at = get_datetime(e.timestamp)
		new_state = "Down" if e.event_type == "Alarm" else e.state
		if at <= start:
			state = new_state
		else:
			changes.append((at, new_state))
	# Cut the period at every state change and every downtime boundary, then classify each piece.
	points = {start, end, *(at for at, _ in changes)}
	points.update(t for s, e, _ in windows for t in (s, e) if start < t < end)
	ordered = sorted(points)
	intervals, change_index = [], 0
	for a, b in pairwise(ordered):
		while change_index < len(changes) and changes[change_index][0] <= a:
			state = changes[change_index][1]
			change_index += 1
		covering = [planned for s, e, planned in windows if s <= a < e]
		if covering:
			intervals.append((minutes_between(a, b), "Down", any(covering)))
		else:
			intervals.append((minutes_between(a, b), state, False))
	return intervals


def downtime_windows(machine: str, start, end) -> list[tuple]:
	"""(start, end, planned) of every Downtime Record overlapping [start, end). An open record runs
	to the end of the period."""
	records = frappe.get_all(
		"Downtime Record",
		filters={"machine": machine, "start_time": ("<", end)},
		or_filters=[["end_time", "is", "not set"], ["end_time", ">=", start]],
		fields=["start_time", "end_time", "reason"],
	)
	planned_reasons = {r.name for r in frappe.get_all("Downtime Reason", {"counts_as_planned": 1}, ["name"])}
	return [
		(
			get_datetime(d.start_time),
			min(get_datetime(d.end_time), end) if d.end_time else end,
			bool(d.reason and d.reason in planned_reasons),
		)
		for d in records
	]


def counts_in(machine: str, start, end) -> tuple[float, float]:
	return good_and_scrap(counter_totals(machine, start, end))


def compute_daily_oee(for_date=None):
	"""Scheduled daily: one OEE Period per enabled machine for each of the previous two days whose
	window has ended and has no period yet.

	A machine with a Shift Start is measured over its scheduled window only, so state time and counts
	outside the shift never enter the period. Without one, the whole day is the planned time. A shift
	that crosses midnight has not ended when the job runs for its date, so it is skipped then and
	created by the next day's run; a window is never computed before it is over.
	"""
	now = now_datetime()
	today = getdate(now)
	days = [getdate(for_date)] if for_date else [add_days(today, -1), add_days(today, -2)]
	machines = frappe.get_all(
		"Machine", {"disabled": 0}, ["name", "scheduled_minutes_per_day", "shift_start"]
	)
	created = []
	for day, m in ((day, m) for day in days for m in machines):
		start, end, planned = scheduled_window(day, m.shift_start, m.scheduled_minutes_per_day)
		if end > now:
			continue
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
