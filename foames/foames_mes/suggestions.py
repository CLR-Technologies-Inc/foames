# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Built-in rules that turn floor data into Agent Suggestions. No Frappe dependency.

Each rule takes a plain snapshot (dicts and lists) and returns suggestion dicts with a `rule_key`
that identifies the finding, so an open suggestion is not raised twice. External agents can add
their own suggestions through the API, and other apps register more rules through the
`foames_suggestion_rules` hook; these rules are the baseline that runs without either.
"""

from __future__ import annotations

SILENT_AFTER_MINUTES = 30
TOP_DOWNTIME_SHARE = 0.5


def all_rules(snapshot: dict) -> list[dict]:
	out = []
	for rule in (silent_machines, dominant_downtime_reason, unresolved_erp_references):
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
