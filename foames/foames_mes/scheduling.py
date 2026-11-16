# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Finite-capacity production scheduling as pure arithmetic. No Frappe dependency.

This is a forward, list-scheduling heuristic of the kind found in most MES and APS tools:

- Each operation belongs to a job and has a sequence number. The operations of a job run one after
  another in sequence order (finish to start, plus an optional transfer time).
- Each operation lists the machines it may run on, with its setup and run minutes on each, because
  the same work can take longer on an older machine.
- Each machine has working windows (its shift calendar) with blocked time (maintenance, planned
  stops) already taken out. Work only advances inside a working window; when splitting is allowed
  an operation pauses over a break and continues in the next window, otherwise it must fit in one
  stretch of working time.
- Among the operations whose predecessor is already placed, a dispatching rule picks the next one
  (EDD, SPT, FIFO, Priority or critical ratio). It goes on the eligible machine where it finishes
  earliest. A machine runs one operation at a time.
- An operation already running on a machine is pinned there and placed first.
- Consecutive operations on one machine that share a setup group skip the second setup.

Nothing here decides what a machine does: the result is a plan for people to publish and follow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

RULES = ("EDD", "SPT", "FIFO", "Priority", "CR")
RULE_LABELS = {
	"EDD": "Earliest due date",
	"SPT": "Shortest processing time",
	"FIFO": "First in, first out",
	"Priority": "Highest priority first",
	"CR": "Critical ratio",
}
FAR_FUTURE = datetime.max


@dataclass
class Operation:
	key: str
	job: str
	sequence: int
	# eligible machine -> (setup minutes, run minutes) on that machine
	machines: dict[str, tuple[float, float]]
	due: datetime | None = None
	release: datetime | None = None
	priority: int = 0  # higher is more urgent
	setup_group: str | None = None
	transfer_minutes: float = 0.0  # wait after the previous operation of the job ends
	pinned_machine: str | None = None  # already running there
	order: int = 0  # arrival order, for FIFO and ties
	label: str = ""


@dataclass
class Slot:
	key: str
	job: str
	sequence: int
	machine: str
	start: datetime
	end: datetime
	setup_minutes: float
	run_minutes: float
	setup_skipped: bool
	pieces: list[tuple[datetime, datetime]]
	due: datetime | None = None

	@property
	def split(self) -> bool:
		return len(self.pieces) > 1

	@property
	def lateness_minutes(self) -> float | None:
		if not self.due:
			return None
		return (self.end - self.due).total_seconds() / 60.0


@dataclass
class Unscheduled:
	key: str
	job: str
	sequence: int
	reason: str


@dataclass
class Schedule:
	start: datetime
	end: datetime
	rule: str
	slots: list[Slot] = field(default_factory=list)
	unscheduled: list[Unscheduled] = field(default_factory=list)
	kpis: dict = field(default_factory=dict)


# Time windows


def merge(intervals) -> list[tuple[datetime, datetime]]:
	"""Sorted, non-overlapping intervals; touching ones are joined so a run of back-to-back shifts
	counts as one stretch of working time."""
	out: list[list[datetime]] = []
	for a, b in sorted((a, b) for a, b in intervals if b > a):
		if out and a <= out[-1][1]:
			out[-1][1] = max(out[-1][1], b)
		else:
			out.append([a, b])
	return [(a, b) for a, b in out]


def subtract(windows, blocks) -> list[tuple[datetime, datetime]]:
	"""`windows` with every `blocks` interval cut out."""
	blocks = merge(blocks)
	out = []
	for a, b in merge(windows):
		cursor = a
		for x, y in blocks:
			if y <= cursor or x >= b:
				continue
			if x > cursor:
				out.append((cursor, x))
			cursor = max(cursor, y)
			if cursor >= b:
				break
		if cursor < b:
			out.append((cursor, b))
	return out


def clip(windows, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
	return [(max(a, start), min(b, end)) for a, b in windows if min(b, end) > max(a, start)]


def minutes(a: datetime, b: datetime) -> float:
	return (b - a).total_seconds() / 60.0


def place(windows, earliest: datetime, duration: float, split: bool = True):
	"""(start, end, pieces) for `duration` working minutes from `earliest` on, or None when the
	windows run out first. With `split` off the work must fit in one window."""
	duration = max(float(duration or 0), 0.0)
	if duration == 0:
		for a, b in windows:
			if b > earliest:
				at = max(a, earliest)
				return at, at, [(at, at)]
		return None
	if not split:
		for a, b in windows:
			begin = max(a, earliest)
			if begin < b and minutes(begin, b) >= duration - 1e-9:
				end = begin + timedelta(minutes=duration)
				return begin, end, [(begin, end)]
		return None
	left = duration
	pieces = []
	for a, b in windows:
		if b <= earliest:
			continue
		begin = max(a, earliest)
		available = minutes(begin, b)
		if available <= 0:
			continue
		take = min(available, left)
		end = begin + timedelta(minutes=take)
		pieces.append((begin, end))
		left -= take
		if left <= 1e-9:
			return pieces[0][0], end, pieces
	return None


# Dispatching


def _due(op: Operation) -> datetime:
	return op.due or FAR_FUTURE


def _fastest(op: Operation) -> float:
	return min((s + r for s, r in op.machines.values()), default=float("inf"))


def rule_key(rule: str, op: Operation, start: datetime, remaining_work: float):
	"""Sort key for the dispatching rule; the smallest key goes next. Pinned operations always
	come first."""
	pinned = 0 if op.pinned_machine else 1
	if rule == "SPT":
		key = (_fastest(op), _due(op))
	elif rule == "FIFO":
		key = ()
	elif rule == "Priority":
		key = (-op.priority, _due(op))
	elif rule == "CR":
		if op.due is None:
			ratio = float("inf")
		else:
			ratio = minutes(start, op.due) / max(remaining_work, 1e-6)
		key = (ratio,)
	else:  # EDD
		key = (_due(op), -op.priority)
	return (pinned, *key, op.order, op.key)


def schedule(
	operations: list[Operation],
	calendars: dict[str, list[tuple[datetime, datetime]]],
	start: datetime,
	end: datetime,
	rule: str = "EDD",
	split: bool = True,
) -> Schedule:
	"""Place `operations` on the machines of `calendars` (machine -> working windows with blocked
	time already removed) between `start` and `end`."""
	if rule not in RULES:
		raise ValueError(f"unknown dispatching rule {rule}")
	if end <= start:
		raise ValueError("the horizon must end after it starts")
	result = Schedule(start=start, end=end, rule=rule)
	windows = {m: clip(merge(w), start, end) for m, w in calendars.items()}
	free_from = {m: start for m in windows}
	last_group: dict[str, str | None] = {}

	jobs: dict[str, list[Operation]] = {}
	keys = set()
	for op in operations:
		if op.key in keys:
			raise ValueError(f"operation {op.key} is listed more than once")
		keys.add(op.key)
		jobs.setdefault(op.job, []).append(op)
	successor: dict[str, Operation | None] = {}
	predecessor: dict[str, Operation | None] = {}
	for ops in jobs.values():
		ops.sort(key=lambda o: (o.sequence, o.order, o.key))
		for i, op in enumerate(ops):
			predecessor[op.key] = ops[i - 1] if i else None
			successor[op.key] = ops[i + 1] if i + 1 < len(ops) else None

	def remaining_work(op: Operation) -> float:
		total, cur = 0.0, op
		while cur:
			total += _fastest(cur) if cur.machines else 0
			cur = successor[cur.key]
		return total

	finished: dict[str, datetime] = {}
	ready = [op for op in operations if predecessor[op.key] is None or op.pinned_machine]
	waiting = {op.key for op in operations} - {op.key for op in ready}

	def drop_successors(op: Operation, reason: str):
		nxt = successor[op.key]
		while nxt and nxt.key in waiting:
			waiting.discard(nxt.key)
			result.unscheduled.append(Unscheduled(nxt.key, nxt.job, nxt.sequence, reason))
			nxt = successor[nxt.key]

	while ready:
		ready.sort(key=lambda o: rule_key(rule, o, start, remaining_work(o)))
		op = ready.pop(0)
		earliest = max(start, op.release or start)
		pred = predecessor[op.key]
		if pred is not None and pred.key in finished and not op.pinned_machine:
			earliest = max(earliest, finished[pred.key] + timedelta(minutes=op.transfer_minutes or 0))
		candidates = [op.pinned_machine] if op.pinned_machine else sorted(op.machines)
		best = None
		reason = "no eligible machine"
		for m in candidates:
			if m not in op.machines:
				continue
			if m not in windows:
				reason = f"machine {m} has no calendar"
				continue
			setup, run = op.machines[m]
			skipped = bool(op.setup_group) and last_group.get(m) == op.setup_group and setup > 0
			need = (0 if skipped else setup) + run
			placed = place(windows[m], max(earliest, free_from[m]), need, split)
			if not placed:
				reason = (
					"no working stretch long enough in the horizon"
					if not split
					else "does not finish inside the horizon"
				)
				continue
			s, e, pieces = placed
			candidate = (e, s, m, setup, run, skipped, pieces)
			if best is None or candidate[:3] < best[:3]:
				best = candidate
		if best is None:
			result.unscheduled.append(Unscheduled(op.key, op.job, op.sequence, reason))
			drop_successors(op, f"waits on {op.label or op.key}, which could not be scheduled")
			continue
		e, s, m, setup, run, skipped, pieces = best
		slot = Slot(
			key=op.key,
			job=op.job,
			sequence=op.sequence,
			machine=m,
			start=s,
			end=e,
			setup_minutes=0.0 if skipped else setup,
			run_minutes=run,
			setup_skipped=skipped,
			pieces=pieces,
			due=op.due,
		)
		result.slots.append(slot)
		finished[op.key] = e
		free_from[m] = e
		last_group[m] = op.setup_group
		nxt = successor[op.key]
		if nxt is not None and nxt.key in waiting:
			waiting.discard(nxt.key)
			ready.append(nxt)

	result.slots.sort(key=lambda s: (s.start, s.machine, s.key))
	result.kpis = kpis(result, windows, jobs)
	return result


def kpis(result: Schedule, windows: dict, jobs: dict[str, list[Operation]]) -> dict:
	"""Headline figures of a schedule: counts, makespan, late jobs, tardiness and machine load."""
	by_job: dict[str, list[Slot]] = {}
	for s in result.slots:
		by_job.setdefault(s.job, []).append(s)
	unscheduled_jobs = {u.job for u in result.unscheduled}
	late_jobs, tardiness = [], 0.0
	for job, ops in jobs.items():
		dues = [o.due for o in ops if o.due]
		if not dues or job in unscheduled_jobs or job not in by_job:
			continue
		done = max(s.end for s in by_job[job])
		late = minutes(min(dues), done)
		if late > 0:
			late_jobs.append(job)
			tardiness += late
	load = {}
	for m, w in windows.items():
		available = sum(minutes(a, b) for a, b in w)
		busy = sum(minutes(a, b) for s in result.slots if s.machine == m for a, b in s.pieces)
		load[m] = {
			"available_minutes": round(available, 2),
			"busy_minutes": round(busy, 2),
			"utilisation": round(busy / available * 100.0, 2) if available else 0.0,
		}
	makespan_end = max((s.end for s in result.slots), default=None)
	return {
		"operations": len(result.slots) + len(result.unscheduled),
		"scheduled": len(result.slots),
		"unscheduled": len(result.unscheduled),
		"jobs": len(jobs),
		"late_jobs": sorted(late_jobs),
		"total_tardiness_minutes": round(tardiness, 2),
		"makespan_end": makespan_end,
		"makespan_minutes": round(minutes(result.start, makespan_end), 2) if makespan_end else 0.0,
		"machine_load": load,
	}


# Following the plan on the floor

BEHIND_STATES = ("Down", "Idle", "Unknown", "Setup")
DEFAULT_GRACE_MINUTES = 15.0


def current_and_next(slots: list[dict], now: datetime, upcoming: int = 3) -> dict:
	"""The slot a machine should be working on now and the next few, from slot dicts with
	`start` and `end`."""
	slots = sorted(slots, key=lambda s: s["start"])
	current = next((s for s in slots if s["start"] <= now < s["end"]), None)
	later = [s for s in slots if s["start"] > now][:upcoming]
	return {"current": current, "next": later}


def behind_schedule_findings(
	machines: list[dict], now: datetime, grace_minutes: float = DEFAULT_GRACE_MINUTES
) -> list[dict]:
	"""Agent Suggestion dicts for machines that should have been running a scheduled operation for
	longer than `grace_minutes` but report Down, Idle, Setup or Unknown.

	Each machine dict has `name`, `status` and `schedule` as made by `current_and_next`; a slot dict
	has `name`, `job`, `operation`, `start`, `end` and `production_schedule`."""
	out = []
	for m in machines:
		slot = (m.get("schedule") or {}).get("current")
		if not slot or m.get("status") not in BEHIND_STATES:
			continue
		late_by = minutes(slot["start"], now)
		if late_by < grace_minutes:
			continue
		what = slot.get("operation") or slot.get("job")
		out.append(
			{
				"rule_key": f"schedule:{slot['name']}:behind",
				"category": "Schedule",
				"severity": "Warning",
				"title": f"{m['name']} is behind schedule on {what}",
				"suggestion": (
					f"{m['name']} should have started {what} for job {slot.get('job')} at {slot['start']:%Y-%m-%d %H:%M} "
					f"but reports {m.get('status')}. Start it, or rebuild the schedule if the plan has changed."
				),
				"reference_doctype": "Scheduled Operation",
				"reference_name": slot["name"],
				"evidence": {
					"machine": m["name"],
					"status": m.get("status"),
					"job": slot.get("job"),
					"operation": slot.get("operation"),
					"planned_start": str(slot["start"]),
					"planned_end": str(slot["end"]),
					"production_schedule": slot.get("production_schedule"),
					"minutes_late": round(late_by, 1),
				},
			}
		)
	return out
