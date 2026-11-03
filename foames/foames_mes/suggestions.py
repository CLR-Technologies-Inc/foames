# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Built-in rules that turn floor data into Agent Suggestions. No Frappe dependency.

Each rule takes a plain snapshot (dicts and lists) and returns suggestion dicts with a `rule_key`
that identifies the finding, so an open suggestion is not raised twice. External agents can add
their own suggestions through the API, and other apps register more rules through the
`foames_suggestion_rules` hook; these rules are the baseline that runs without either.
"""

from __future__ import annotations

from foames.foames_mes.counters import good_and_scrap, resource_totals

SILENT_AFTER_MINUTES = 30
TOP_DOWNTIME_SHARE = 0.5


def all_rules(snapshot: dict) -> list[dict]:
	out = []
	for rule in (
		silent_machines,
		dominant_downtime_reason,
		unresolved_erp_references,
		resource_without_output,
	):
		out.extend(rule(snapshot))
	return out


def silent_machines(snapshot: dict) -> list[dict]:
	"""Machines that counted recently and have since gone quiet, or report Running without counting."""
	out = []
	for m in snapshot.get("machines", []):
		minutes = m.get("minutes_since_count")
		if minutes is None or minutes < SILENT_AFTER_MINUTES:
			continue
		if m.get("status") == "Unknown":
			out.append(
				{
					"rule_key": f"silent:{m['name']}:{m.get('last_seen')}",
					"category": "Machine Data",
					"severity": "Warning",
					"title": f"{m['name']} went silent after counting",
					"suggestion": f"No event from {m['name']} since {m.get('last_seen')}, {minutes:.0f} minutes after its last count. Check the gateway, the network or the PLC program before trusting its counts.",
					"reference_doctype": "Machine",
					"reference_name": m["name"],
					"evidence": {"last_seen": m.get("last_seen"), "minutes_since_count": minutes},
				}
			)
		elif m.get("status") == "Running":
			out.append(
				{
					"rule_key": f"stalled:{m['name']}:{m.get('last_seen')}",
					"category": "Downtime",
					"severity": "Warning",
					"title": f"{m['name']} reports Running but has not counted for {minutes:.0f} minutes",
					"suggestion": f"Machine {m['name']} is in state Running with no count for {minutes:.0f} minutes. Either it is starved or blocked and should be Idle, or the counter signal is lost.",
					"reference_doctype": "Machine",
					"reference_name": m["name"],
					"evidence": {"minutes_since_count": minutes, "status": m.get("status")},
				}
			)
	return out


def dominant_downtime_reason(snapshot: dict) -> list[dict]:
	out = []
	for m in snapshot.get("downtime_by_machine", []):
		total = m.get("total_minutes") or 0
		top = m.get("top_reason")
		if total <= 0 or not top:
			continue
		share = (m.get("top_minutes") or 0) / total
		if share >= TOP_DOWNTIME_SHARE:
			out.append(
				{
					"rule_key": f"downtime:{m['machine']}:{top}:{m.get('period')}",
					"category": "Downtime",
					"severity": "Info",
					"title": f"{top} is {share:.0%} of downtime on {m['machine']}",
					"suggestion": f"Over {m.get('period')}, {top} caused {m['top_minutes']:.0f} of {total:.0f} downtime minutes on {m['machine']}. A single cause this large is the first target for a kaizen or a changeover (SMED) study.",
					"reference_doctype": "Machine",
					"reference_name": m["machine"],
					"evidence": {
						"top_reason": top,
						"top_minutes": m["top_minutes"],
						"total_minutes": total,
						"period": m.get("period"),
					},
				}
			)
	return out


def unresolved_erp_references(snapshot: dict) -> list[dict]:
	missing = [r for r in snapshot.get("external_references", []) if r.get("status") == "Missing"]
	if not missing:
		return []
	names = ", ".join(f"{r['reference_type']} {r['external_id']}" for r in missing[:10])
	return [
		{
			"rule_key": f"erp-missing:{len(missing)}:{missing[0]['name']}",
			"category": "ERP",
			"severity": "Warning",
			"title": f"{len(missing)} ERP references point to records that do not exist",
			"suggestion": f"These references resolved as Missing in the ERP: {names}. Create the records or correct the ids, then resolve the references again.",
			"evidence": {"missing": [r["name"] for r in missing]},
		}
	]


def resource_without_output(snapshot: dict) -> list[dict]:
	"""Machines whose metered inputs (energy, water, feed) advanced over the window while their
	production counters did not.

	Electrified and continuous processes are judged by consumption per unit of product, and the
	worst case of that ratio is a unit that draws its full load while making nothing: a plasma or
	electrolysis reactor held at power during a feed stop, a furnace kept hot through a shift with
	no orders. The time may well be booked as Idle or Down already; this rule puts a number on what
	the idle time cost. One finding per machine and resource per day.
	"""
	out = []
	date = str(snapshot.get("as_of") or "")[:10]
	for m in snapshot.get("machines", []):
		counts = m.get("counts") or {}
		good, scrap = good_and_scrap(counts)
		if good + scrap > 0:
			continue
		for name, used in resource_totals(counts).items():
			if used <= 0:
				continue
			out.append(
				{
					"rule_key": f"resource-idle:{m['name']}:{name}:{date}",
					"category": "Yield",
					"severity": "Warning",
					"title": f"{m['name']} consumed {used:g} {name} with no output",
					"suggestion": f"Over the window {m['name']} metered {used:g} on counter {name} and counted no production. If the machine was idle or down, that consumption is pure loss: look at whether it can be powered down or put in standby when there is no feed or no order. If it was producing, the production counter is not reaching FoaMES.",
					"reference_doctype": "Machine",
					"reference_name": m["name"],
					"evidence": {
						"counter": name,
						"consumed": used,
						"good": good,
						"scrap": scrap,
						"status": m.get("status"),
						"as_of": str(snapshot.get("as_of") or ""),
					},
				}
			)
	return out
