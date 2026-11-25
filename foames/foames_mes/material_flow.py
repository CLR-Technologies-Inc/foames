# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Material flow on the site: reads lineside stock from the ERP, estimates what the machines have
used since, forecasts when each line runs dry, keeps queue readiness current, and raises Agent
Suggestions. The arithmetic is in `material.py`.

Stock is read, never written. Each reader registered in the `foames_stock_readers` hook is called
with (item, location) and returns a dict with at least `actual_qty`, or None when it does not know
the item. The ERPNext adapter registers one that reads ERPNext's Bin table. Calling material for a
bin, consuming it against a job and posting the movement stay in the ERP, done by people; FoaMES
tells them what to call for and when.
"""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime

from foames.foames_mes import material as m
from foames.foames_mes.counters import good_and_scrap

AGENT = "foames-material"
STOCK_TOLERANCE = 1e-6
OPEN = ("Waiting", "In Process", "On Hold")


# Stock ---------------------------------------------------------------------------------------------


def read_stock(item: str, location: str | None = None) -> dict | None:
	"""The first answer from the registered stock readers, or None when no reader knows the item.

	A reader that fails is logged and skipped, so one unreachable ERP never stops the check."""
	for path in frappe.get_hooks("foames_stock_readers") or []:
		try:
			result = frappe.get_attr(path)(item, location)
		except Exception:
			frappe.log_error(title=f"FoaMES stock reader {path}", message=frappe.get_traceback())
			continue
		if result is not None:
			return result
	return None


def units_produced(machine: str | None, since, until=None) -> float:
	"""Good plus scrap units a machine counted in a window, from the stored counter deltas."""
	if not machine or not since:
		return 0.0
	event = frappe.qb.DocType("Machine Event")
	from frappe.query_builder.functions import Sum

	query = (
		frappe.qb.from_(event)
		.select(event.counter_name, Sum(event.delta).as_("total"))
		.where((event.machine == machine) & (event.event_type == "Count") & (event.timestamp >= since))
		.groupby(event.counter_name)
	)
	if until is not None:
		query = query.where(event.timestamp < until)
	totals = {r.counter_name: r.total or 0 for r in query.run(as_dict=True)}
	good, scrap = good_and_scrap(totals)
	return float(good + scrap)


def _profile(name: str | None) -> dict:
	if not name:
		return {"level": 1, "conditioning_minutes": 0}
	doc = frappe.get_cached_doc("Material Handling Profile", name)
	return m.mpc(doc.as_dict())


def refresh_bin(name: str, now=None) -> dict:
	"""Read one bin's stock, estimate consumption since, assess it and store the result. Returns the
	row bin_findings expects."""
	now = get_datetime(now) if now else now_datetime()
	doc = frappe.get_doc("Lineside Bin", name)
	values: dict = {"last_checked": now}
	read_qty = float(doc.read_qty or 0)
	last_read_at = get_datetime(doc.last_read_at) if doc.last_read_at else None

	consumed = 0.0
	if last_read_at:
		consumed = m.consumption(
			units_produced(doc.machine, last_read_at, now), doc.quantity_per_unit, doc.scrap_allowance_percent
		)
	estimate = m.estimated_on_hand(read_qty, consumed)

	if doc.stock_source == "ERP":
		stock = read_stock(doc.item, doc.location)
		if stock is not None:
			fresh = float(stock.get("actual_qty") or 0)
			if last_read_at is None or fresh > estimate + STOCK_TOLERANCE:
				# More stock than the estimate allows: a replenishment arrived (or this is the first read).
				values["last_replenished_at"] = now
			read_qty, last_read_at, consumed, estimate = fresh, now, 0.0, max(fresh, 0.0)
			values.update({"read_qty": fresh, "last_read_at": now})

	window = float(doc.rate_window_hours or 2) or 2
	per_hour = m.rate_per_hour(
		m.consumption(
			units_produced(doc.machine, now - timedelta(hours=window), now),
			doc.quantity_per_unit,
			doc.scrap_allowance_percent,
		),
		window,
	)
	profile = _profile(doc.material_profile)
	assessment = m.assess_bin(
		doc.as_dict(), estimate, per_hour, profile["level"], profile.get("conditioning_minutes") or 0
	)
	dry_at = m.dry_at(now, assessment["hours_to_dry"])
	values.update(
		{
			"consumed_since_read": consumed,
			"on_hand": estimate,
			"per_hour": per_hour,
			"status": assessment["status"],
			"hours_to_dry": assessment["hours_to_dry"],
			"dry_at": dry_at,
			"replenish_qty": assessment["replenish_qty"],
			"mpc_level": profile["level"],
		}
	)
	if doc.replenishment_method == "Kanban" and doc.container_qty and per_hour:
		values["recommended_kanban_cards"] = m.kanban_cards(
			per_hour, assessment["lead_hours"], doc.container_qty, doc.warn_margin_percent or 0
		)
	frappe.db.set_value("Lineside Bin", name, values, update_modified=False)
	return {
		"name": name,
		"title": doc.title,
		"machine": doc.machine,
		"item": doc.item,
		"uom": doc.uom,
		"mpc_level": profile["level"],
		"assessment": assessment,
		"dry_at": dry_at,
		"cycle": str(values.get("last_replenished_at") or doc.last_replenished_at or ""),
	}


# Queues --------------------------------------------------------------------------------------------

ENTRY_FIELDS = (
	"name",
	"item",
	"batch",
	"quantity",
	"uom",
	"status",
	"priority",
	"due_at",
	"arrived_at",
	"min_wait_minutes",
	"max_wait_minutes",
	"expires_at",
	"mpc_level",
	"job_reference",
)


def open_entries(queue: str) -> list[dict]:
	return frappe.get_all(
		"Material Queue Entry",
		filters={"queue": queue, "status": ["in", OPEN]},
		fields=list(ENTRY_FIELDS),
		order_by="arrived_at asc",
	)


def queue_row(queue: str, now) -> dict:
	q = frappe.db.get_value(
		"Material Queue",
		queue,
		["name", "title", "machine", "discipline", "capacity", "qtime_warn_percent", "last_activity"],
		as_dict=True,
	)
	q["machine_status"] = frappe.db.get_value("Machine", q.machine, "status") if q.machine else None
	q["entries"] = open_entries(queue)
	q["last_activity"] = str(q.last_activity or "")
	return q


def refresh_queue(queue: str, now=None) -> dict:
	"""Store each open entry's readiness and the queue's counts. Returns the row queue_findings expects."""
	now = get_datetime(now) if now else now_datetime()
	q = queue_row(queue, now)
	for e in q["entries"]:
		r = m.readiness(e, now, q.qtime_warn_percent)
		frappe.db.set_value(
			"Material Queue Entry",
			e["name"],
			{"readiness": r["state"], "ready_at": r["ready_at"], "limit_at": r["limit_at"]},
			update_modified=False,
		)
	s = m.queue_summary(q, q["entries"], now)
	frappe.db.set_value(
		"Material Queue",
		queue,
		{
			"waiting_count": s["waiting"],
			"ready_count": s["ready"],
			"waiting_quantity": s["quantity"],
			"oldest_wait_minutes": s["oldest_wait_minutes"],
			"last_checked": now,
		},
		update_modified=False,
	)
	return q


def dispatch_list(queue: str, now=None) -> list[dict]:
	"""Entries that may start now, in the order the queue's dispatch rule picks them."""
	now = get_datetime(now) if now else now_datetime()
	q = queue_row(queue, now)
	waiting = [e for e in q["entries"] if e.status == "Waiting"]
	ordered = m.dispatch_order(waiting, q.discipline or "FIFO", now, q.qtime_warn_percent)
	return [
		{
			**{k: e.get(k) for k in ENTRY_FIELDS},
			"state": e["readiness"]["state"],
			"minutes_to_limit": e["readiness"]["minutes_to_limit"],
		}
		for e in ordered
	]


# The scheduled check -------------------------------------------------------------------------------


def check_material_flow(now=None) -> list[str]:
	"""Scheduled every 10 minutes: refresh every enabled bin and queue and raise suggestions for bins
	running dry, queue entries near or past their limits, starved machines and full buffers. Returns
	the suggestions created or reopened."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	now = get_datetime(now) if now else now_datetime()
	bins = []
	for name in frappe.get_all("Lineside Bin", filters={"disabled": 0}, pluck="name", order_by="name"):
		try:
			bins.append(refresh_bin(name, now))
		except Exception:
			frappe.log_error(title=f"FoaMES lineside bin {name}", message=frappe.get_traceback())
	queues = []
	for name in frappe.get_all("Material Queue", filters={"disabled": 0}, pluck="name", order_by="name"):
		try:
			queues.append(refresh_queue(name, now))
		except Exception:
			frappe.log_error(title=f"FoaMES material queue {name}", message=frappe.get_traceback())
	return raise_suggestions(m.bin_findings(bins) + m.queue_findings(queues, now), agent=AGENT)


# The floor and the scheduler -----------------------------------------------------------------------

BIN_FIELDS = (
	"name",
	"title",
	"machine",
	"item",
	"uom",
	"status",
	"on_hand",
	"per_hour",
	"hours_to_dry",
	"dry_at",
	"replenish_qty",
	"mpc_level",
	"last_checked",
)
QUEUE_FIELDS = (
	"name",
	"title",
	"machine",
	"discipline",
	"capacity",
	"waiting_count",
	"ready_count",
	"waiting_quantity",
	"oldest_wait_minutes",
	"last_checked",
)


def extend_snapshot(snapshot: dict, since, now) -> None:
	"""Floor snapshot extension: lineside bins and queues as last checked, and a per-machine summary."""
	if not (
		frappe.has_permission("Lineside Bin", "read") and frappe.has_permission("Material Queue", "read")
	):
		return
	bins = frappe.get_all("Lineside Bin", filters={"disabled": 0}, fields=list(BIN_FIELDS), order_by="name")
	queues = frappe.get_all(
		"Material Queue", filters={"disabled": 0}, fields=list(QUEUE_FIELDS), order_by="name"
	)
	snapshot["material"] = {"bins": bins, "queues": queues}
	for machine in snapshot.get("machines", []):
		machine["material"] = machine_summary(machine["name"], bins, queues)


def machine_summary(machine: str, bins: list[dict], queues: list[dict]) -> dict:
	mine = [b for b in bins if b.get("machine") == machine]
	at_risk = [b for b in mine if b.get("status") in ("Running Dry", "Will Run Dry", "Dry")]
	hours = [b["hours_to_dry"] for b in mine if b.get("hours_to_dry") is not None]
	feeding = [q for q in queues if q.get("machine") == machine]
	return {
		"bins": len(mine),
		"bins_at_risk": len(at_risk),
		"dry": any(b.get("status") == "Dry" for b in mine),
		"hours_to_dry": min(hours) if hours else None,
		"queue_waiting": sum(int(q.get("waiting_count") or 0) for q in feeding),
		"queue_ready": sum(int(q.get("ready_count") or 0) for q in feeding),
	}


def material_readiness(machine: str, hours: float = 0) -> dict:
	"""Whether a machine has the material to run for `hours`: for a scheduler deciding what to start.

	Short: bins that run dry inside the window (or are dry now). Ready: entries in its queues that may
	start now. A scheduler can call this before it dispatches an operation to the machine."""
	bins = frappe.get_all(
		"Lineside Bin", filters={"disabled": 0, "machine": machine}, fields=list(BIN_FIELDS)
	)
	short = [
		b
		for b in bins
		if b.status == "Dry" or (b.hours_to_dry is not None and hours and b.hours_to_dry < hours)
	]
	ready = []
	for queue in frappe.get_all("Material Queue", filters={"disabled": 0, "machine": machine}, pluck="name"):
		ready.extend({**e, "queue": queue} for e in dispatch_list(queue))
	return {"machine": machine, "hours": hours, "ok": not short, "short": short, "ready": ready}
