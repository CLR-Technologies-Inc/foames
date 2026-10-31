# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Process-mining API for the desk, for scripts and for external agents (for example over MCP).

Every method takes an optional window and source list and works on a log built on the fly, or
on a saved Process Event Log by name. Results are plain dicts.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from foames.foames_process_mining import conformance, discovery
from foames.foames_process_mining.eventlog import EventLog, event_to_dict
from foames.foames_process_mining.extractors import build_event_log
from foames.foames_process_mining.ocel import to_ocel_json
from foames.foames_process_mining.xes import to_xes


def _log(event_log: str | None, since, until, sources) -> EventLog:
	frappe.has_permission("Process Event Log", "read", throw=True)
	if event_log:
		return frappe.get_doc("Process Event Log", event_log).load()
	return build_event_log(since, until, _list(sources))


def _list(value):
	if isinstance(value, str):
		value = (
			json.loads(value) if value.startswith("[") else [v.strip() for v in value.split(",") if v.strip()]
		)
	return value or None


@frappe.whitelist()
def summary(event_log: str | None = None, since=None, until=None, sources=None) -> dict:
	return _log(event_log, since, until, sources).summary()


@frappe.whitelist()
def events(
	event_log: str | None = None, since=None, until=None, sources=None, limit: int = 1000
) -> list[dict]:
	events = _log(event_log, since, until, sources).events
	if limit:
		events = events[: int(limit)]
	return [event_to_dict(e) for e in events]


@frappe.whitelist()
def discover(
	event_log: str | None = None,
	since=None,
	until=None,
	sources=None,
	min_edge_count: int = 1,
	dot: bool = False,
) -> dict:
	"""The directly-follows graph, variants, throughput, bottlenecks and rework for the log."""
	log = _log(event_log, since, until, sources)
	dfg = discovery.discover_dfg(log).filter(min_edge_count=int(min_edge_count))
	result = {
		"summary": log.summary(),
		"dfg": dfg.to_dict(),
		"variants": discovery.variant_table(log, limit=25),
		"throughput": discovery.throughput(log),
		"activities": discovery.activity_durations(log),
		"bottlenecks": discovery.bottlenecks(log),
		"rework": discovery.rework(log),
	}
	if frappe.utils.cint(dot):
		result["dot"] = dfg.to_dot()
	return result


@frappe.whitelist()
def check_conformance(
	model, event_log: str | None = None, since=None, until=None, sources=None, include_traces: bool = True
) -> dict:
	"""Replay the log on a reference model.

	`model` is one of: a DFG dict as returned by `discover` (`{"edges": [...], ...}`), a JSON list
	of activity names for a strict sequence, or the name of a saved Process Event Log whose
	discovered graph is the reference."""
	log = _log(event_log, since, until, sources)
	reference = _model(model)
	report = conformance.check_conformance(log, reference)
	return {
		**report.to_dict(include_traces=frappe.utils.cint(include_traces)),
		"footprint": conformance.compare_footprints(reference, discovery.discover_dfg(log)),
	}


def _model(model) -> discovery.DirectlyFollowsGraph:
	if isinstance(model, str):
		text = model.strip()
		if text.startswith(("{", "[")):
			model = json.loads(text)
		else:
			frappe.has_permission("Process Event Log", "read", throw=True)
			return discovery.discover_dfg(frappe.get_doc("Process Event Log", text).load())
	if isinstance(model, list):
		return conformance.model_from_sequence([str(step) for step in model])
	if isinstance(model, dict):
		return discovery.DirectlyFollowsGraph.from_dict(model)
	frappe.throw(_("The model must be a DFG dict, a list of activities or a Process Event Log name"))


@frappe.whitelist()
def export(event_log: str | None = None, since=None, until=None, sources=None, fmt: str = "xes") -> str:
	"""The log as XES XML or OCEL 2.0 JSON text, for any external process-mining tool."""
	log = _log(event_log, since, until, sources)
	fmt = (fmt or "xes").lower()
	if fmt == "xes":
		return to_xes(log)
	if fmt in ("ocel", "ocel2", "json"):
		return to_ocel_json(log)
	frappe.throw(_("Unknown format {0}; use xes or ocel").format(fmt))
