# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Conformance checking: does the floor run the process the way the model says?

The reference model is a directly-follows graph: allowed activities, allowed transitions, allowed
start and end activities. It can be written by hand, discovered from a golden period, or supplied
by another app. Each trace is replayed against it and every move is classified; fitness is the
share of conforming moves, which is the token-replay fitness for this model class. Footprint
matrices (the Alpha-miner relations ->, <-, || and #) compare two models cell by cell.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from foames.foames_process_mining.discovery import DirectlyFollowsGraph, discover_dfg
from foames.foames_process_mining.eventlog import COMPLETE, EventLog

FOLLOWS, PRECEDES, PARALLEL, NEVER = "->", "<-", "||", "#"


@dataclass
class TraceResult:
	case_id: str
	steps: list[str]
	fitness: float
	deviations: list[dict] = field(default_factory=list)

	@property
	def conforms(self) -> bool:
		return not self.deviations


@dataclass
class ConformanceReport:
	cases: int
	conforming_cases: int
	fitness: float
	traces: list[TraceResult]
	deviation_counts: dict[str, int]

	def to_dict(self, include_traces: bool = True) -> dict:
		data = {
			"cases": self.cases,
			"conforming_cases": self.conforming_cases,
			"conformance_rate": (self.conforming_cases / self.cases) if self.cases else None,
			"fitness": self.fitness,
			"deviation_counts": dict(self.deviation_counts),
		}
		if include_traces:
			data["traces"] = [
				{"case_id": t.case_id, "steps": t.steps, "fitness": t.fitness, "deviations": t.deviations}
				for t in self.traces
				if t.deviations
			]
		return data


def check_conformance(
	log: EventLog, model: DirectlyFollowsGraph, lifecycle: str | None = COMPLETE
) -> ConformanceReport:
	"""Replay every trace on the model. Deviations are: an unknown activity, a wrong start, a
	transition the model does not allow, and a wrong end. A trace's fitness is 1 minus the share
	of its moves (start, each transition, end) that deviate."""
	allowed_edges = set(model.edges)
	allowed_activities = set(model.activities) | {a for e in model.edges for a in e}
	starts, ends = set(model.start_activities), set(model.end_activities)
	results: list[TraceResult] = []
	counts: dict[str, int] = {}

	for case_id, events in log.traces().items():
		steps = [e.activity for e in events if lifecycle is None or e.lifecycle == lifecycle]
		if not steps:
			continue
		deviations = []
		moves = len(steps) + 1  # start move, one move per transition, end move
		if steps[0] not in starts and starts:
			deviations.append({"kind": "wrong_start", "activity": steps[0], "position": 0})
		for position, activity in enumerate(steps):
			if activity not in allowed_activities:
				deviations.append({"kind": "unknown_activity", "activity": activity, "position": position})
			if position and (steps[position - 1], activity) not in allowed_edges:
				known = steps[position - 1] in allowed_activities and activity in allowed_activities
				if known:
					deviations.append(
						{
							"kind": "disallowed_transition",
							"from": steps[position - 1],
							"to": activity,
							"position": position,
						}
					)
		if steps[-1] not in ends and ends:
			deviations.append({"kind": "wrong_end", "activity": steps[-1], "position": len(steps) - 1})
		fitness = max(0.0, 1 - len(deviations) / moves)
		for deviation in deviations:
			counts[deviation["kind"]] = counts.get(deviation["kind"], 0) + 1
		results.append(TraceResult(case_id, steps, fitness, deviations))

	conforming = sum(1 for r in results if r.conforms)
	fitness = sum(r.fitness for r in results) / len(results) if results else 1.0
	return ConformanceReport(len(results), conforming, fitness, results, counts)


def footprint(model: DirectlyFollowsGraph) -> dict[str, dict[str, str]]:
	"""The Alpha relations between every pair of activities, from the directly-follows edges."""
	activities = sorted(set(model.activities) | {a for e in model.edges for a in e})
	edges = set(model.edges)
	matrix: dict[str, dict[str, str]] = {}
	for a in activities:
		matrix[a] = {}
		for b in activities:
			ab, ba = (a, b) in edges, (b, a) in edges
			matrix[a][b] = PARALLEL if ab and ba else FOLLOWS if ab else PRECEDES if ba else NEVER
	return matrix


def compare_footprints(reference: DirectlyFollowsGraph, observed: DirectlyFollowsGraph) -> dict:
	"""Cell-by-cell comparison of two footprints; the score is the share of agreeing cells over
	the union of activities. Lists every disagreement so the difference can be read."""
	ref, obs = footprint(reference), footprint(observed)
	activities = sorted(set(ref) | set(obs))
	differences = []
	agree = 0
	for a in activities:
		for b in activities:
			r = ref.get(a, {}).get(b, NEVER)
			o = obs.get(a, {}).get(b, NEVER)
			if r == o:
				agree += 1
			else:
				differences.append({"from": a, "to": b, "reference": r, "observed": o})
	total = len(activities) ** 2
	return {
		"activities": activities,
		"score": (agree / total) if total else 1.0,
		"differences": differences,
		"missing_in_observed": sorted(set(ref) - set(obs)),
		"new_in_observed": sorted(set(obs) - set(ref)),
	}


def model_from_log(
	log: EventLog, min_edge_count: int = 1, lifecycle: str | None = COMPLETE
) -> DirectlyFollowsGraph:
	"""A reference model discovered from a log of known-good runs, with rare edges filtered."""
	return discover_dfg(log, lifecycle).filter(min_edge_count=min_edge_count)


def model_from_sequence(steps: list[str], allow_repeats: bool = False) -> DirectlyFollowsGraph:
	"""A strictly sequential model: a -> b -> c with a the only start and c the only end. With
	allow_repeats, an activity may follow itself."""
	model = DirectlyFollowsGraph(cases=1)
	for step in steps:
		model.activities[step] += 1
	for a, b in itertools.pairwise(steps):
		model.edges[(a, b)] += 1
	if allow_repeats:
		for step in steps:
			model.edges[(step, step)] += 1
	if steps:
		model.start_activities[steps[0]] += 1
		model.end_activities[steps[-1]] += 1
	return model
