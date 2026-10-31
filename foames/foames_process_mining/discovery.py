# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Process discovery and performance analysis over an event log.

The directly-follows graph (DFG) is the model every discovery algorithm starts from: an edge
a -> b counted every time b directly follows a in a trace, with the time between them. Filtering
the DFG by frequency is the pragmatic discovery most tools show first, and it already answers the
floor questions: which paths are taken, how often, how long they take, and where work waits.
"""

from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, median

from foames.foames_process_mining.eventlog import COMPLETE, START, Event, EventLog, seconds_between

Edge = tuple[str, str]


@dataclass
class DirectlyFollowsGraph:
	activities: Counter = field(default_factory=Counter)
	edges: Counter = field(default_factory=Counter)
	durations: dict[Edge, list[float]] = field(default_factory=lambda: defaultdict(list))  # seconds
	start_activities: Counter = field(default_factory=Counter)
	end_activities: Counter = field(default_factory=Counter)
	cases: int = 0

	def successors(self, activity: str) -> dict[str, int]:
		return {b: n for (a, b), n in self.edges.items() if a == activity}

	def predecessors(self, activity: str) -> dict[str, int]:
		return {a: n for (a, b), n in self.edges.items() if b == activity}

	def edge_stats(self, edge: Edge) -> dict:
		values = self.durations.get(edge) or []
		return {
			"count": self.edges.get(edge, 0),
			"mean_seconds": mean(values) if values else None,
			"median_seconds": median(values) if values else None,
			"max_seconds": max(values) if values else None,
		}

	def filter(self, min_edge_count: int = 1, min_activity_count: int = 1) -> DirectlyFollowsGraph:
		"""Drop rare activities and edges. Start and end counts are kept for surviving activities."""
		keep = {a for a, n in self.activities.items() if n >= min_activity_count}
		out = DirectlyFollowsGraph(cases=self.cases)
		out.activities = Counter({a: n for a, n in self.activities.items() if a in keep})
		out.edges = Counter(
			{e: n for e, n in self.edges.items() if n >= min_edge_count and e[0] in keep and e[1] in keep}
		)
		out.durations = defaultdict(list, {e: list(self.durations[e]) for e in out.edges})
		out.start_activities = Counter({a: n for a, n in self.start_activities.items() if a in keep})
		out.end_activities = Counter({a: n for a, n in self.end_activities.items() if a in keep})
		return out

	def to_dict(self) -> dict:
		return {
			"cases": self.cases,
			"activities": dict(self.activities),
			"start_activities": dict(self.start_activities),
			"end_activities": dict(self.end_activities),
			"edges": [
				{"from": a, "to": b, **self.edge_stats((a, b))}
				for (a, b) in sorted(self.edges, key=lambda e: -self.edges[e])
			],
		}

	@classmethod
	def from_dict(cls, data: dict) -> DirectlyFollowsGraph:
		dfg = cls(cases=int(data.get("cases") or 0))
		dfg.activities = Counter(data.get("activities") or {})
		dfg.start_activities = Counter(data.get("start_activities") or {})
		dfg.end_activities = Counter(data.get("end_activities") or {})
		for edge in data.get("edges") or []:
			dfg.edges[(edge["from"], edge["to"])] = int(edge.get("count") or 1)
		for a in list(dfg.edges):
			dfg.activities.setdefault(a[0], 0)
			dfg.activities.setdefault(a[1], 0)
		return dfg

	def to_dot(self, label_durations: bool = True) -> str:
		"""Graphviz DOT, for a quick picture in any viewer."""
		lines = [
			"digraph dfg {",
			"\trankdir=LR;",
			'\tnode [shape=box, style="rounded,filled", fillcolor="#eef3f8"];',
		]
		for activity, count in self.activities.items():
			lines.append(f'\t{_dot_id(activity)} [label="{_escape(activity)}\\n{count}"];')
		lines.append('\t__start [shape=circle, label="", fillcolor="#2e7d32"];')
		lines.append('\t__end [shape=doublecircle, label="", fillcolor="#c62828"];')
		for activity, count in self.start_activities.items():
			lines.append(f'\t__start -> {_dot_id(activity)} [label="{count}"];')
		for (a, b), count in self.edges.items():
			label = str(count)
			stats = self.edge_stats((a, b))
			if label_durations and stats["median_seconds"] is not None:
				label += f"\\n{format_duration(stats['median_seconds'])}"
			lines.append(f'\t{_dot_id(a)} -> {_dot_id(b)} [label="{label}"];')
		for activity, count in self.end_activities.items():
			lines.append(f'\t{_dot_id(activity)} -> __end [label="{count}"];')
		lines.append("}")
		return "\n".join(lines)


def discover_dfg(log: EventLog, lifecycle: str | None = COMPLETE) -> DirectlyFollowsGraph:
	"""Count directly-follows relations per trace. Only events with the given lifecycle count as
	steps (so a start/complete pair is one activity); pass None to use every event."""
	dfg = DirectlyFollowsGraph()
	for events in log.traces().values():
		steps = [e for e in events if lifecycle is None or e.lifecycle == lifecycle]
		if not steps:
			continue
		dfg.cases += 1
		dfg.start_activities[steps[0].activity] += 1
		dfg.end_activities[steps[-1].activity] += 1
		for event in steps:
			dfg.activities[event.activity] += 1
		for previous, current in itertools.pairwise(steps):
			edge = (previous.activity, current.activity)
			dfg.edges[edge] += 1
			dfg.durations[edge].append(seconds_between(previous.timestamp, current.timestamp))
	return dfg


def variant_table(log: EventLog, limit: int | None = None) -> list[dict]:
	"""Variants with their share of cases and case-duration statistics."""
	traces = log.traces()
	rows = []
	total = len(traces) or 1
	for steps, case_ids in log.variants().items():
		durations = [_case_duration(traces[c]) for c in case_ids]
		rows.append(
			{
				"variant": list(steps),
				"cases": len(case_ids),
				"share": len(case_ids) / total,
				"median_duration_seconds": median(durations) if durations else None,
				"example_case": case_ids[0],
			}
		)
	return rows[:limit] if limit else rows


def case_durations(log: EventLog) -> dict[str, float]:
	"""Seconds from a case's first to its last event."""
	return {case_id: _case_duration(events) for case_id, events in log.traces().items()}


def throughput(log: EventLog) -> dict:
	"""Case-level cycle time statistics, in seconds, and cases completed per day over the span."""
	durations = list(case_durations(log).values())
	span = log.span()
	# A rate needs an observed span; a log whose events share one timestamp has none.
	days = seconds_between(span[0], span[1]) / 86400 if span else 0
	return {
		"cases": len(durations),
		"mean_seconds": mean(durations) if durations else None,
		"median_seconds": median(durations) if durations else None,
		"min_seconds": min(durations) if durations else None,
		"max_seconds": max(durations) if durations else None,
		"cases_per_day": (len(durations) / days) if days > 0 else None,
	}


def activity_durations(log: EventLog) -> dict[str, dict]:
	"""Service time per activity from start/complete pairs within a case, plus the waiting time
	before each activity (complete of the previous step to start of this one). Activities logged
	with only complete events get no service time and a waiting time measured from the previous
	complete."""
	service: dict[str, list[float]] = defaultdict(list)
	waiting: dict[str, list[float]] = defaultdict(list)
	for events in log.traces().values():
		open_starts: dict[str, datetime] = {}
		last_complete: datetime | None = None
		for event in events:
			if event.lifecycle == START:
				open_starts[event.activity] = event.timestamp
				if last_complete is not None:
					waiting[event.activity].append(seconds_between(last_complete, event.timestamp))
			elif event.lifecycle == COMPLETE:
				started = open_starts.pop(event.activity, None)
				if started is not None:
					service[event.activity].append(seconds_between(started, event.timestamp))
				elif last_complete is not None:
					waiting[event.activity].append(seconds_between(last_complete, event.timestamp))
				last_complete = event.timestamp
	activities = set(service) | set(waiting)
	return {
		activity: {
			"count": len(service.get(activity) or waiting.get(activity) or []),
			"waiting_count": len(waiting.get(activity) or []),
			"median_service_seconds": median(service[activity]) if service.get(activity) else None,
			"mean_service_seconds": mean(service[activity]) if service.get(activity) else None,
			"median_waiting_seconds": median(waiting[activity]) if waiting.get(activity) else None,
			"mean_waiting_seconds": mean(waiting[activity]) if waiting.get(activity) else None,
		}
		for activity in sorted(activities)
	}


def bottlenecks(log: EventLog, limit: int = 3) -> list[dict]:
	"""Activities ranked by total waiting time in front of them: where cases queue."""
	stats = activity_durations(log)
	ranked = []
	for activity, row in stats.items():
		if row["mean_waiting_seconds"] is None:
			continue
		ranked.append(
			{
				"activity": activity,
				"total_waiting_seconds": row["mean_waiting_seconds"] * row["waiting_count"],
				"median_waiting_seconds": row["median_waiting_seconds"],
				"count": row["waiting_count"],
			}
		)
	ranked.sort(key=lambda r: -r["total_waiting_seconds"])
	return ranked[:limit]


def rework(log: EventLog) -> dict[str, int]:
	"""How many cases repeat each activity: a repeat is rework or a loop, both worth a look."""
	repeats: Counter = Counter()
	for events in log.traces().values():
		seen = Counter(e.activity for e in events if e.lifecycle == COMPLETE)
		for activity, n in seen.items():
			if n > 1:
				repeats[activity] += 1
	return dict(repeats)


def format_duration(seconds: float) -> str:
	delta = timedelta(seconds=round(seconds))
	days, rest = divmod(int(delta.total_seconds()), 86400)
	hours, rest = divmod(rest, 3600)
	minutes, secs = divmod(rest, 60)
	if days:
		return f"{days}d {hours}h"
	if hours:
		return f"{hours}h {minutes}m"
	if minutes:
		return f"{minutes}m {secs}s"
	return f"{secs}s"


def _case_duration(events: list[Event]) -> float:
	return seconds_between(events[0].timestamp, events[-1].timestamp) if events else 0.0


def _dot_id(activity: str) -> str:
	return '"' + _escape(activity) + '"'


def _escape(text: str) -> str:
	return text.replace("\\", "\\\\").replace('"', '\\"')
