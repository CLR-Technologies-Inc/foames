# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Process FMEA arithmetic as published practice, with no Frappe dependency.

A PFMEA rates each failure chain (effect, mode, cause) on three 1 to 10 scales:

- Severity (S) of the failure effect,
- Occurrence (O) of the failure cause, given the prevention controls,
- Detection (D) of the cause or mode, given the detection controls (10 means it is not detected).

Risk is ranked by the Action Priority (AP) table of the AIAG and VDA FMEA Handbook (first edition,
2019), which puts severity first, then occurrence, then detection, instead of multiplying them. High
means an action must be identified or the decision not to act justified; Medium means an action
should be identified; Low means one could be. The older Risk Priority Number (S x O x D) is kept
alongside for plants that still report it.

Occurrence can be checked against what the floor actually records: incidents per thousand units
produced map to an occurrence rating with the incidents-per-thousand scale published in the AIAG
PFMEA manual (fourth edition) and repeated as an alternative occurrence table in the AIAG and VDA
handbook. The observed rating is a prompt for the FMEA team, never an automatic re-rating.
"""

from __future__ import annotations

from datetime import date, datetime

RATING_MIN, RATING_MAX = 1, 10
PRIORITIES = ("H", "M", "L")
PRIORITY_LABELS = {"H": "High", "M": "Medium", "L": "Low"}

# Occurrence rows of the AP table, by severity band. Each band maps an occurrence band to the
# priority for the detection bands (7-10, 5-6, 2-4, 1), in that order.
_D_BANDS = ((7, 10), (5, 6), (2, 4), (1, 1))
_O_BANDS = ((8, 10), (6, 7), (4, 5), (2, 3), (1, 1))
_AP_TABLE = {
	(9, 10): ("HHHH", "HHHH", "HHHM", "HMLL", "LLLL"),
	(7, 8): ("HHHH", "HHHM", "HMMM", "MMLL", "LLLL"),
	(4, 6): ("HHMM", "MMML", "MLLL", "LLLL", "LLLL"),
	(2, 3): ("MMLL", "LLLL", "LLLL", "LLLL", "LLLL"),
	(1, 1): ("LLLL", "LLLL", "LLLL", "LLLL", "LLLL"),
}

# Incidents per thousand units at or above which each occurrence rating applies, highest first.
# 10: 1 in 10, 9: 1 in 20, 8: 1 in 50, 7: 1 in 100, 6: 1 in 500, 5: 1 in 2,000, 4: 1 in 10,000,
# 3: 1 in 100,000, 2: 1 in 1,000,000 or fewer. Rating 1 means the cause is prevented by design,
# which no observed rate can show, so an observed rate never maps below 2.
OCCURRENCE_PER_THOUSAND = (
	(100.0, 10),
	(50.0, 9),
	(20.0, 8),
	(10.0, 7),
	(2.0, 6),
	(0.5, 5),
	(0.1, 4),
	(0.01, 3),
)

ACTION_STATUSES = ("Open", "Decision Pending", "Implementation Pending", "Completed", "Not Implemented")
CLOSED_ACTION_STATUSES = ("Completed", "Not Implemented")


def valid_rating(value) -> bool:
	try:
		number = float(value)
	except (TypeError, ValueError):
		return False
	return number.is_integer() and RATING_MIN <= number <= RATING_MAX


def _band(value: int, bands) -> int:
	for index, (low, high) in enumerate(bands):
		if low <= value <= high:
			return index
	raise ValueError(f"rating {value} is outside {RATING_MIN} to {RATING_MAX}")


def action_priority(severity, occurrence, detection) -> str | None:
	"""H, M or L from the AIAG-VDA table, or None while any rating is missing or out of range."""
	if not all(valid_rating(r) for r in (severity, occurrence, detection)):
		return None
	s, o, d = int(severity), int(occurrence), int(detection)
	rows = next(rows for (low, high), rows in _AP_TABLE.items() if low <= s <= high)
	return rows[_band(o, _O_BANDS)][_band(d, _D_BANDS)]


def rpn(severity, occurrence, detection) -> int | None:
	"""The legacy Risk Priority Number S x O x D, or None while any rating is missing."""
	if not all(valid_rating(r) for r in (severity, occurrence, detection)):
		return None
	return int(severity) * int(occurrence) * int(detection)


def per_thousand(incidents: float, units: float) -> float | None:
	"""Incidents per thousand units, or None when nothing was produced (no basis for a rate)."""
	if not units or units <= 0:
		return None
	return max(float(incidents or 0), 0.0) / float(units) * 1000.0


def occurrence_from_rate(rate_per_thousand: float | None) -> int | None:
	"""The occurrence rating an observed incident rate supports, or None without a rate."""
	if rate_per_thousand is None:
		return None
	for threshold, rating in OCCURRENCE_PER_THOUSAND:
		if rate_per_thousand >= threshold:
			return rating
	return 2


def rate_for_occurrence(occurrence: int) -> float | None:
	"""The lowest incidents per thousand that the rating stands for (the band's floor)."""
	for threshold, rating in OCCURRENCE_PER_THOUSAND:
		if rating == occurrence:
			return threshold
	return None


def summarize(items: list[dict]) -> dict:
	"""Counts for a PFMEA header: rows by current action priority and actions still open."""
	counts = {"H": 0, "M": 0, "L": 0}
	open_actions = 0
	for item in items:
		ap = item.get("action_priority")
		if ap in counts:
			counts[ap] += 1
		if has_action(item) and item.get("action_status") not in CLOSED_ACTION_STATUSES:
			open_actions += 1
	return {"high": counts["H"], "medium": counts["M"], "low": counts["L"], "open_actions": open_actions}


def has_action(item: dict) -> bool:
	return bool((item.get("prevention_action") or "").strip() or (item.get("detection_action") or "").strip())


def check_item(item: dict) -> list[str]:
	"""Problems that stop a row from being saved, as messages. Ratings may be left empty in a draft."""
	problems = []
	for field in ("severity", "occurrence", "detection", "new_severity", "new_occurrence", "new_detection"):
		value = item.get(field)
		if value not in (None, "", 0) and not valid_rating(value):
			problems.append(f"{field.replace('_', ' ').title()} must be a whole number from 1 to 10")
	status = item.get("action_status")
	if status and status not in ACTION_STATUSES:
		problems.append(f"Unknown action status {status}")
	if status == "Completed":
		if not all(valid_rating(item.get(f)) for f in ("new_severity", "new_occurrence", "new_detection")):
			problems.append("A completed action needs the revised severity, occurrence and detection")
		if not item.get("completion_date"):
			problems.append("A completed action needs its completion date")
	if status == "Not Implemented" and not (item.get("action_taken") or "").strip():
		problems.append("Record why the action was not implemented")
	if status and not has_action(item):
		problems.append("An action status needs a prevention or detection action")
	return problems


def check_release(items: list[dict]) -> list[str]:
	"""Problems that stop a PFMEA from being released: every row needs its three ratings."""
	if not items:
		return ["A PFMEA needs at least one failure mode before it is released"]
	problems = []
	for index, item in enumerate(items, start=1):
		missing = [f for f in ("severity", "occurrence", "detection") if not valid_rating(item.get(f))]
		if missing:
			problems.append(f"Row {index} needs {', '.join(missing)}")
	return problems


# Suggestions


def _label(item: dict) -> str:
	step = " ".join(str(p) for p in (item.get("op_no"), item.get("process_step")) if p)
	mode = (item.get("failure_mode") or "").strip()
	return f"{step}: {mode}" if step and mode else step or mode or f"row {item.get('idx')}"


def _key(pfmea: str, item: dict, *parts) -> str:
	return ":".join(["pfmea", pfmea, str(item.get("row") or item.get("idx")), *(str(p) for p in parts)])


def findings(pfmea: dict, items: list[dict], today: date | datetime) -> list[dict]:
	"""Agent Suggestion dicts for a released PFMEA's rows.

	`pfmea` carries name and title; each item carries the row fields plus `row` (its stable id) and,
	when observed, observed_occurrence, observed_per_thousand, observed_units, observed_incidents and
	spc_signals. Raised:

	- the observed occurrence is above the rated one (the rating no longer matches the floor),
	- SPC signals on the row's measured characteristic,
	- a High action priority with no action and no recorded decision,
	- an action past its target date.
	"""
	today = today.date() if isinstance(today, datetime) else today
	name, title = pfmea["name"], pfmea.get("title") or pfmea["name"]
	out = []
	for item in items:
		label = _label(item)
		base = {"category": "Quality", "reference_doctype": "PFMEA", "reference_name": name}
		rated, observed = item.get("occurrence"), item.get("observed_occurrence")
		if valid_rating(rated) and observed and int(observed) > int(rated):
			ap_now = action_priority(item.get("severity"), observed, item.get("detection"))
			out.append(
				{
					**base,
					"rule_key": _key(name, item, "occurrence", int(observed)),
					"severity": "Critical" if ap_now == "H" else "Warning",
					"title": f"{label} occurs more often than {title} rates it",
					"suggestion": " ".join(
						[
							f"The floor recorded {item.get('observed_incidents', 0):,.0f} incidents in",
							f"{item.get('observed_units', 0):,.0f} units",
							f"({item.get('observed_per_thousand', 0):.3g} per thousand),",
							f"which supports occurrence {int(observed)}; the PFMEA rates it {int(rated)}.",
							f"At the observed occurrence the action priority is {PRIORITY_LABELS.get(ap_now, 'unknown')}.",
							"Review the prevention controls and the occurrence rating with the FMEA team.",
						]
					),
					"evidence": {
						"row": item.get("row"),
						"rated_occurrence": int(rated),
						"observed_occurrence": int(observed),
						"per_thousand": item.get("observed_per_thousand"),
						"incidents": item.get("observed_incidents"),
						"units": item.get("observed_units"),
						"action_priority_at_observed": ap_now,
					},
				}
			)
		if item.get("spc_signals"):
			out.append(
				{
					**base,
					"rule_key": _key(name, item, "spc"),
					"severity": "Critical" if int(item.get("severity") or 0) >= 9 else "Warning",
					"title": f"SPC signals on {item.get('measurement_name')} for {label}",
					"suggestion": " ".join(
						[
							f"{item['spc_signals']} SPC signal(s) on {item.get('measurement_name')}",
							f"at {item.get('machine') or 'the line'} since {item.get('observed_since')}.",
							"The PFMEA relies on it as a control for this failure mode",
							f"(detection {item.get('detection')}).",
							"Check the cause, apply the reaction plan, and review the occurrence and detection ratings.",
						]
					),
					"evidence": {
						"row": item.get("row"),
						"signals": item["spc_signals"],
						"latest_signal_at": item.get("latest_signal_at"),
					},
				}
			)
		ap = item.get("action_priority")
		if ap == "H" and not has_action(item) and item.get("action_status") != "Not Implemented":
			out.append(
				{
					**base,
					"rule_key": _key(name, item, "high-without-action"),
					"severity": "Warning",
					"title": f"High action priority without an action: {label}",
					"suggestion": " ".join(
						[
							f"{title} rates this chain S{item.get('severity')} O{item.get('occurrence')}",
							f"D{item.get('detection')}, High priority.",
							"Identify a prevention or detection action, or record why none is taken",
							"(status Not Implemented with the reason).",
						]
					),
					"evidence": {"row": item.get("row"), "action_priority": ap},
				}
			)
		target = item.get("target_date")
		if target and item.get("action_status") not in CLOSED_ACTION_STATUSES and has_action(item):
			target = target.date() if isinstance(target, datetime) else target
			if isinstance(target, str):
				target = date.fromisoformat(target[:10])
			if target < today:
				out.append(
					{
						**base,
						"rule_key": _key(name, item, "overdue", target.isoformat()),
						"severity": "Warning" if ap != "H" else "Critical",
						"title": f"PFMEA action overdue: {label}",
						"suggestion": " ".join(
							[
								f"The action for {label} in {title} was due on {target.isoformat()}",
								f"and is {item.get('action_status') or 'Open'}"
								+ (
									f"; it is assigned to {item['responsible']}."
									if item.get("responsible")
									else "."
								),
								"Complete it and re-rate the chain, or move the target date.",
							]
						),
						"evidence": {"row": item.get("row"), "target_date": target.isoformat()},
					}
				)
	return out
