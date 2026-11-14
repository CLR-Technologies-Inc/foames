# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Environmental health and safety as pure logic: incident classification and rates, the 5 x 5 risk
matrix and the hierarchy of controls, exposure arithmetic, permit-to-work rules and the findings
they raise. No Frappe dependency.

Everything here is established public practice:

- Recordability follows the general recording criteria of US OSHA 29 CFR 1904.7: a work-related
  case is recordable when it results in death, days away from work, restricted work or job
  transfer, medical treatment beyond first aid, loss of consciousness, or a significant diagnosed
  injury or illness. Day counts are capped at 180 (1904.7(b)(3)(vii)). The most serious outcome is
  the one a log records (Form 300 columns G to J).
- Incidence rates are normalised to 200,000 hours worked (100 full-time workers for a year), the
  base used by the US Bureau of Labor Statistics: TRIR, DART and the lost-time rate.
- The risk matrix is the common 5 x 5 likelihood by severity grid; the hierarchy of controls is
  the NIOSH order (elimination, substitution, engineering, administrative, PPE), also the order in
  ISO 45001 clause 8.1.2.
- An 8-hour time-weighted average counts unsampled time as zero exposure (29 CFR 1910.1000(d)).
  Noise dose uses the OSHA 5 dB exchange rate (29 CFR 1910.95 Appendix A): T = 8 / 2^((L - 90) / 5)
  hours, D = 100 * sum(C / T), TWA = 16.61 * log10(D / 100) + 90.
- Permits to work follow the usual lockout/tagout practice (29 CFR 1910.147): every isolation point
  locked and verified at zero energy before the work starts, every lock removed before the permit
  closes, issuer and performer different people.

FoaMES never stops a machine or writes a tag (agents suggest; people act): a machine that reports
Running while a lockout permit on it is active raises a Critical suggestion for a person.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

# Incidents

INCIDENT_TYPES = (
	"Near Miss",
	"Unsafe Condition",
	"Unsafe Act",
	"First Aid",
	"Injury or Illness",
	"Property Damage",
	"Environmental Release",
)
# Types that can be an injury or illness case on the log.
PERSONAL_TYPES = ("First Aid", "Injury or Illness")
# Leading indicators: events that hurt nobody.
LEADING_TYPES = ("Near Miss", "Unsafe Condition", "Unsafe Act")
INCIDENT_STATUSES = ("Reported", "Investigating", "Actions Open", "Closed")

OUTCOMES = ("Death", "Days Away From Work", "Job Transfer or Restriction", "Other Recordable Case")
DAY_CAP = 180
RATE_BASE_HOURS = 200_000.0
# Days from the event within which an incident should have a root cause.
INVESTIGATION_DAYS = 7


def capped_days(days) -> int:
	"""Days away or restricted as a log counts them: whole days, never negative, at most 180."""
	return min(max(int(days or 0), 0), DAY_CAP)


def osha_outcome(
	*,
	death: bool = False,
	days_away: int = 0,
	days_restricted: int = 0,
	medical_treatment: bool = False,
	loss_of_consciousness: bool = False,
	significant_diagnosis: bool = False,
) -> str | None:
	"""The most serious outcome of a case, or None when it is not recordable (first aid only)."""
	if death:
		return "Death"
	if capped_days(days_away) > 0:
		return "Days Away From Work"
	if capped_days(days_restricted) > 0:
		return "Job Transfer or Restriction"
	if medical_treatment or loss_of_consciousness or significant_diagnosis:
		return "Other Recordable Case"
	return None


def classify_incident(incident: dict) -> dict:
	"""Recordability of an incident dict.

	Only work-related Injury or Illness cases can be recordable; a First Aid case that turns out to
	need more than first aid has to be changed to Injury or Illness, so the log never counts a case
	the record still calls first aid. Returns recordable, outcome, dart (days away, restricted or
	transferred), lost_time (days away or death) and the capped day counts.
	"""
	outcome = None
	if incident.get("incident_type") == "Injury or Illness" and incident.get("work_related", 1):
		outcome = osha_outcome(
			death=bool(incident.get("death")),
			days_away=incident.get("days_away"),
			days_restricted=incident.get("days_restricted"),
			medical_treatment=bool(incident.get("medical_treatment")),
			loss_of_consciousness=bool(incident.get("loss_of_consciousness")),
			significant_diagnosis=bool(incident.get("significant_diagnosis")),
		)
	days_away = capped_days(incident.get("days_away")) if outcome else 0
	days_restricted = capped_days(incident.get("days_restricted")) if outcome else 0
	return {
		"recordable": outcome is not None,
		"outcome": outcome,
		"dart": outcome in ("Days Away From Work", "Job Transfer or Restriction"),
		"lost_time": outcome in ("Death", "Days Away From Work"),
		"days_away": days_away,
		"days_restricted": days_restricted,
	}


def incidence_rate(cases: float, hours_worked: float) -> float | None:
	"""Cases per 200,000 hours worked; None when no hours are known."""
	if not hours_worked or hours_worked <= 0:
		return None
	return cases * RATE_BASE_HOURS / hours_worked


def incident_rates(incidents: list[dict], hours_worked: float | None) -> dict:
	"""Counts and rates over a list of incident dicts (the fields classify_incident reads, plus
	incident_type).

	DART counts cases with days away, restriction or transfer; a death is counted as recordable and
	as lost time but not in DART, as on BLS tables. The near-miss ratio is leading events (near
	misses, unsafe conditions and acts) per recordable case; None with no recordables.
	"""
	counts = dict.fromkeys(INCIDENT_TYPES, 0)
	recordable = dart = lost_time = days_away = days_restricted = 0
	for incident in incidents:
		kind = incident.get("incident_type")
		if kind in counts:
			counts[kind] += 1
		c = classify_incident(incident)
		recordable += c["recordable"]
		dart += c["dart"]
		lost_time += c["lost_time"]
		days_away += c["days_away"]
		days_restricted += c["days_restricted"]
	leading = sum(counts[t] for t in LEADING_TYPES)
	return {
		"incidents": len(incidents),
		"by_type": counts,
		"recordable": recordable,
		"dart": dart,
		"lost_time": lost_time,
		"days_away": days_away,
		"days_restricted": days_restricted,
		"leading": leading,
		"hours_worked": hours_worked or None,
		"trir": incidence_rate(recordable, hours_worked),
		"dart_rate": incidence_rate(dart, hours_worked),
		"ltir": incidence_rate(lost_time, hours_worked),
		"severity_rate": incidence_rate(days_away, hours_worked),
		"near_miss_ratio": leading / recordable if recordable else None,
	}


# Risk


LIKELIHOOD = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost Certain"}
SEVERITY = {1: "Negligible", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Catastrophic"}
RISK_LEVELS = ("Low", "Medium", "High", "Very High")
CONTROL_HIERARCHY = ("Elimination", "Substitution", "Engineering", "Administrative", "PPE")


def _scale(value, name: str) -> int:
	try:
		number = float(value)
	except (TypeError, ValueError):
		number = math.nan
	if not number.is_integer() or not 1 <= number <= 5:
		raise ValueError(f"{name} must be a whole number from 1 to 5")
	return int(number)


def risk_score(likelihood, severity) -> int:
	"""Likelihood times severity on the 5 x 5 matrix, 1 to 25."""
	return _scale(likelihood, "Likelihood") * _scale(severity, "Severity")


def risk_level(score: int) -> str:
	"""1-4 Low, 5-9 Medium, 10-16 High, 20-25 Very High."""
	if score <= 4:
		return "Low"
	if score <= 9:
		return "Medium"
	if score <= 16:
		return "High"
	return "Very High"


def strongest_control(levels) -> str | None:
	"""The most effective level of the hierarchy among the controls given, or None."""
	ranked = [CONTROL_HIERARCHY.index(level) for level in levels if level in CONTROL_HIERARCHY]
	return CONTROL_HIERARCHY[min(ranked)] if ranked else None


def assess_hazard(
	likelihood, severity, residual_likelihood=None, residual_severity=None, control_levels=()
) -> dict:
	"""Inherent and residual risk of a hazard, with the problems a reviewer should see.

	Without a residual estimate the residual risk is the inherent risk. A residual risk above the
	inherent one is refused; a High or Very High residual risk controlled only by administrative
	measures or PPE is reported as a weakness (the hierarchy asks for something stronger first).
	"""
	score = risk_score(likelihood, severity)
	if residual_likelihood or residual_severity:
		residual = risk_score(residual_likelihood or likelihood, residual_severity or severity)
	else:
		residual = score
	if residual > score:
		raise ValueError("the residual risk cannot be higher than the risk before controls")
	strongest = strongest_control(control_levels)
	weaknesses = []
	if risk_level(residual) in ("High", "Very High"):
		if strongest is None:
			weaknesses.append("no controls recorded")
		elif CONTROL_HIERARCHY.index(strongest) >= CONTROL_HIERARCHY.index("Administrative"):
			weaknesses.append(f"relies on {strongest.lower()} controls only")
	return {
		"risk_score": score,
		"risk_level": risk_level(score),
		"residual_score": residual,
		"residual_level": risk_level(residual),
		"strongest_control": strongest,
		"weaknesses": weaknesses,
	}


def next_review(reviewed_on: date | datetime | None, interval_days) -> date | None:
	if not reviewed_on or not interval_days or int(interval_days) <= 0:
		return None
	start = reviewed_on.date() if isinstance(reviewed_on, datetime) else reviewed_on
	return start + timedelta(days=int(interval_days))


# Exposure

METHODS = ("Concentration", "Noise")
EXPOSURE_STATUSES = ("No Limit Set", "Below Action Level", "At or Above Action Level", "Above Limit")
SHIFT_MINUTES = 480.0
NOISE_LIMIT_DBA = 90.0
NOISE_ACTION_DBA = 85.0
# Sound below the threshold does not count towards the dose.
NOISE_THRESHOLD_DBA = 80.0


def twa(samples, shift_minutes: float = SHIFT_MINUTES) -> float:
	"""Time-weighted average of (value, minutes) samples over the shift. Unsampled time is zero
	exposure; sampling longer than the shift averages over the time actually sampled."""
	samples = [(float(v or 0), float(m or 0)) for v, m in samples]
	if any(m < 0 or v < 0 for v, m in samples):
		raise ValueError("sample values and durations cannot be negative")
	total_minutes = sum(m for _, m in samples)
	if not total_minutes:
		return 0.0
	base = max(float(shift_minutes or SHIFT_MINUTES), total_minutes)
	return sum(v * m for v, m in samples) / base


def noise_allowed_hours(level_dba: float) -> float:
	"""Reference duration at a sound level on the OSHA 5 dB exchange rate (8 h at 90 dBA)."""
	return 8.0 / 2 ** ((level_dba - 90.0) / 5.0)


def noise_dose(samples, threshold: float = NOISE_THRESHOLD_DBA) -> float:
	"""Daily noise dose in percent from (dBA, minutes) samples; levels below the threshold count zero."""
	dose = 0.0
	for level, minutes in samples:
		level, minutes = float(level or 0), float(minutes or 0)
		if minutes < 0:
			raise ValueError("sample durations cannot be negative")
		if level < threshold:
			continue
		dose += (minutes / 60.0) / noise_allowed_hours(level)
	return dose * 100.0


def noise_twa(dose_percent: float) -> float | None:
	"""Eight-hour TWA sound level equivalent to a dose; None for no dose."""
	if not dose_percent or dose_percent <= 0:
		return None
	return 16.61 * math.log10(dose_percent / 100.0) + 90.0


def exposure_status(result, limit=None, action_level=None) -> str:
	if result is None:
		return "Below Action Level" if (limit or action_level) else "No Limit Set"
	if limit and result > limit:
		return "Above Limit"
	if action_level and result >= action_level:
		return "At or Above Action Level"
	if not limit and not action_level:
		return "No Limit Set"
	return "Below Action Level"


def evaluate_exposure(method: str, samples, limit=None, action_level=None, shift_minutes=None) -> dict:
	"""Result, dose (noise only) and status of an exposure record. Noise defaults to the OSHA 90 dBA
	limit and 85 dBA action level when none is given."""
	if method == "Noise":
		dose = noise_dose(samples)
		result = noise_twa(dose)
		limit = limit or NOISE_LIMIT_DBA
		action_level = action_level or NOISE_ACTION_DBA
	elif method == "Concentration":
		dose = None
		result = twa(samples, shift_minutes or SHIFT_MINUTES)
	else:
		raise ValueError(f"unknown exposure method {method!r}")
	if limit and action_level and action_level > limit:
		raise ValueError("the action level cannot be above the limit")
	return {
		"result": result,
		"dose_percent": dose,
		"limit": limit,
		"action_level": action_level,
		"status": exposure_status(result, limit, action_level),
		"percent_of_limit": (result / limit * 100.0) if (result is not None and limit) else None,
	}


# Permits to work

PERMIT_TYPES = (
	"Lockout Tagout",
	"Hot Work",
	"Confined Space",
	"Working at Height",
	"Electrical",
	"Line Break",
	"Excavation",
	"General",
)
# Types whose work needs energy isolated first.
ISOLATING_TYPES = ("Lockout Tagout", "Confined Space", "Line Break", "Electrical")
PERMIT_STATUSES = ("Draft", "Active", "Suspended", "Closed", "Cancelled", "Expired")
ENERGY_TYPES = (
	"Electrical",
	"Mechanical",
	"Hydraulic",
	"Pneumatic",
	"Thermal",
	"Chemical",
	"Gravity",
	"Other",
)
DEFAULT_MAX_PERMIT_HOURS = 12.0


def permit_problems(permit: dict, max_hours: float | None = DEFAULT_MAX_PERMIT_HOURS) -> list[str]:
	"""What stops a permit dict from being in its status. Empty when it is fine.

	A permit carries permit_type, status, valid_from, valid_to, issued_by, performed_by and
	isolation_points (dicts with isolation_point, lock_id, verified, removed_on).
	"""
	problems = []
	start, end = permit.get("valid_from"), permit.get("valid_to")
	if start and end:
		if end <= start:
			problems.append("the permit must end after it starts")
		elif max_hours and (end - start).total_seconds() > float(max_hours) * 3600 + 1e-6:
			problems.append(
				f"a permit can be valid for at most {max_hours:g} hours; raise a new one for the next shift"
			)
	status = permit.get("status") or "Draft"
	points = permit.get("isolation_points") or []
	if status == "Active":
		if not (start and end):
			problems.append("an active permit needs a start and an end")
		if not permit.get("issued_by"):
			problems.append("an active permit needs the person who issued it")
		if not permit.get("performed_by"):
			problems.append("an active permit needs the person who does the work")
		if permit.get("issued_by") and permit.get("issued_by") == permit.get("performed_by"):
			problems.append("the issuer cannot also be the person doing the work")
		if permit.get("permit_type") in ISOLATING_TYPES and not points:
			problems.append(f"a {permit.get('permit_type')} permit needs at least one isolation point")
		for p in points:
			label = p.get("isolation_point") or "an isolation point"
			if p.get("removed_on"):
				continue
			if not p.get("lock_id"):
				problems.append(f"{label} has no lock applied")
			if not p.get("verified"):
				problems.append(f"{label} is not verified at zero energy")
	if status == "Closed":
		for p in points:
			if p.get("lock_id") and not p.get("removed_on"):
				problems.append(
					f"the lock on {p.get('isolation_point') or 'an isolation point'} has not been removed"
				)
	return problems


def locks_applied(permit: dict) -> list[str]:
	"""The isolation points of a permit that are still locked out."""
	return [
		p.get("isolation_point") or "?"
		for p in permit.get("isolation_points") or []
		if p.get("lock_id") and not p.get("removed_on")
	]


def is_expired(permit: dict, now: datetime) -> bool:
	return (
		permit.get("status") in ("Active", "Suspended")
		and bool(permit.get("valid_to"))
		and now > permit["valid_to"]
	)


# Findings (Agent Suggestion dicts)


def lockout_findings(machines: list[dict], permits: list[dict]) -> list[dict]:
	"""A machine reporting Running while an active permit holds locks on it.

	machines: dicts with name, status, last_seen. permits: active permit dicts with name, machine,
	permit_type, performed_by and isolation_points.
	"""
	running = {m["name"]: m for m in machines if m.get("status") == "Running"}
	out = []
	for permit in permits:
		machine = running.get(permit.get("machine"))
		locks = locks_applied(permit)
		if not machine or not locks:
			continue
		out.append(
			{
				"rule_key": f"ehs-running-under-lockout:{permit['name']}:{machine.get('last_seen')}",
				"category": "Safety",
				"severity": "Critical",
				"title": f"{machine['name']} reports Running under {permit.get('permit_type', 'permit')} {permit['name']}",
				"suggestion": (
					f"Machine {machine['name']} reports Running while permit {permit['name']} is active with "
					f"{len(locks)} isolation point(s) locked ({', '.join(locks)}). Either the isolation is not "
					"effective, the machine's state signal is wrong, or the permit should have been closed. "
					f"Stop the work and check with {permit.get('performed_by') or 'the permit holder'} before anyone goes on."
				),
				"reference_doctype": "Safety Permit",
				"reference_name": permit["name"],
				"evidence": {
					"machine": machine["name"],
					"machine_status": machine.get("status"),
					"last_seen": str(machine.get("last_seen")),
					"permit_type": permit.get("permit_type"),
					"locked_points": locks,
				},
			}
		)
	return out


def expired_permit_findings(permits: list[dict], now: datetime) -> list[dict]:
	"""Permits past their end that are still active or suspended."""
	out = []
	for permit in permits:
		if not is_expired(permit, now):
			continue
		locks = locks_applied(permit)
		severity = "Critical" if locks else "Warning"
		lock_note = (
			f" {len(locks)} lock(s) are still applied ({', '.join(locks)}): remove them under a new permit or close this one properly."
			if locks
			else ""
		)
		out.append(
			{
				"rule_key": f"ehs-permit-expired:{permit['name']}",
				"category": "Safety",
				"severity": severity,
				"title": f"Permit {permit['name']} expired on {permit['valid_to']}",
				"suggestion": (
					f"{permit.get('permit_type', 'Permit')} {permit['name']}"
					f"{' on ' + permit['machine'] if permit.get('machine') else ''} ran out at {permit['valid_to']}. "
					f"Work under an expired permit is not authorised.{lock_note}"
				),
				"reference_doctype": "Safety Permit",
				"reference_name": permit["name"],
				"evidence": {
					"valid_to": str(permit["valid_to"]),
					"status": permit.get("status"),
					"locked_points": locks,
				},
			}
		)
	return out


def overdue_action_findings(actions: list[dict], today: date) -> list[dict]:
	"""Open corrective actions past their due date. Each action dict has parent, name, action,
	action_owner and due_on."""
	out = []
	for a in actions:
		if not a.get("due_on") or a["due_on"] >= today:
			continue
		days = (today - a["due_on"]).days
		out.append(
			{
				"rule_key": f"ehs-action-overdue:{a['parent']}:{a['name']}",
				"category": "Safety",
				"severity": "Critical" if days > 30 else "Warning",
				"title": f"Corrective action on {a['parent']} is {days} day(s) overdue",
				"suggestion": (
					f'The action "{a.get("action")}" from incident {a["parent"]} was due on {a["due_on"]}'
					f"{' and is owned by ' + a['action_owner'] if a.get('action_owner') else ' and has no owner'}. "
					"Finish it, or record why the risk is controlled another way."
				),
				"reference_doctype": "Safety Incident",
				"reference_name": a["parent"],
				"evidence": {"action": a.get("action"), "due_on": str(a["due_on"]), "days_overdue": days},
			}
		)
	return out


def investigation_findings(incidents: list[dict], today: date, days: int = INVESTIGATION_DAYS) -> list[dict]:
	"""Incidents still without a root cause more than `days` after they happened."""
	out = []
	for i in incidents:
		occurred = i["occurred_on"].date() if isinstance(i["occurred_on"], datetime) else i["occurred_on"]
		age = (today - occurred).days
		if i.get("root_cause") or age <= days or i.get("status") == "Closed":
			continue
		recordable = bool(i.get("recordable"))
		out.append(
			{
				"rule_key": f"ehs-investigation-overdue:{i['name']}",
				"category": "Safety",
				"severity": "Critical" if recordable else "Warning",
				"title": f"{i.get('incident_type', 'Incident')} {i['name']} has no root cause after {age} days",
				"suggestion": (
					f"{i.get('incident_type', 'Incident')} {i['name']}"
					f"{' on ' + i['machine'] if i.get('machine') else ''} happened {age} days ago and has no root cause "
					f"recorded. Investigate it while people still remember{' (it is a recordable case)' if recordable else ''}."
				),
				"reference_doctype": "Safety Incident",
				"reference_name": i["name"],
				"evidence": {
					"occurred_on": str(i["occurred_on"]),
					"status": i.get("status"),
					"recordable": recordable,
				},
			}
		)
	return out


def hazard_review_findings(hazards: list[dict], today: date) -> list[dict]:
	"""Active hazard assessments past their review date, and High residual risks with weak controls."""
	out = []
	for h in hazards:
		if h.get("next_review_on") and h["next_review_on"] < today:
			out.append(
				{
					"rule_key": f"ehs-hazard-review:{h['name']}:{h['next_review_on']}",
					"category": "Safety",
					"severity": "Warning",
					"title": f"Hazard assessment {h.get('title') or h['name']} is due for review",
					"suggestion": (
						f"Hazard assessment {h['name']}{' on ' + h['machine'] if h.get('machine') else ''} was due for "
						f"review on {h['next_review_on']}. Check the controls still work and the risk is still right."
					),
					"reference_doctype": "Hazard Assessment",
					"reference_name": h["name"],
					"evidence": {
						"next_review_on": str(h["next_review_on"]),
						"residual_level": h.get("residual_level"),
					},
				}
			)
		for weakness in h.get("weaknesses") or []:
			out.append(
				{
					"rule_key": f"ehs-hazard-weak-controls:{h['name']}:{h.get('residual_score')}",
					"category": "Safety",
					"severity": "Warning",
					"title": f"{h.get('residual_level')} risk in {h.get('title') or h['name']} {weakness}",
					"suggestion": (
						f"Hazard assessment {h['name']} leaves a {h.get('residual_level', '').lower()} residual risk and "
						f"{weakness}. Look for elimination, substitution or an engineering control first."
					),
					"reference_doctype": "Hazard Assessment",
					"reference_name": h["name"],
					"evidence": {
						"residual_score": h.get("residual_score"),
						"strongest_control": h.get("strongest_control"),
					},
				}
			)
	return out


def exposure_findings(record: dict) -> list[dict]:
	"""An exposure record at or above the action level."""
	status = record.get("status")
	if status not in ("At or Above Action Level", "Above Limit"):
		return []
	unit = record.get("unit") or ""
	who = (
		record.get("exposure_group") or record.get("location") or record.get("machine") or "the group sampled"
	)
	return [
		{
			"rule_key": f"ehs-exposure:{record['name']}:{status}",
			"category": "Safety",
			"severity": "Critical" if status == "Above Limit" else "Warning",
			"title": f"{record.get('agent')} exposure {status.lower()} for {who}",
			"suggestion": (
				f"Exposure record {record['name']} measured {record.get('agent')} at {record.get('result'):.2f} {unit} "
				f"against a limit of {record.get('limit') or '-'} {unit} and an action level of "
				f"{record.get('action_level') or '-'} {unit}. "
				+ (
					"Reduce the exposure now, by engineering controls first, and protect the people exposed until it is."
					if status == "Above Limit"
					else "Start the program the action level calls for (monitoring, training, protection) and look at controls."
				)
			),
			"reference_doctype": "Exposure Record",
			"reference_name": record["name"],
			"evidence": {
				"result": record.get("result"),
				"limit": record.get("limit"),
				"action_level": record.get("action_level"),
				"dose_percent": record.get("dose_percent"),
			},
		}
	]


SERIOUS_POTENTIAL = 4


def serious_incident_findings(incident: dict) -> list[dict]:
	"""A newly reported incident that people above the line should hear about at once: a recordable
	case, a release reportable to an authority, or anything with a potential severity of 4 or 5
	(serious injury and fatality potential, whether or not anyone was hurt)."""
	reasons = []
	if incident.get("recordable"):
		reasons.append(f"it is a recordable case ({incident.get('osha_outcome') or 'recordable'})")
	if incident.get("reportable_release"):
		reasons.append("the release is reportable to an authority")
	if int(incident.get("potential_severity") or 0) >= SERIOUS_POTENTIAL:
		reasons.append(f"its potential severity is {incident['potential_severity']} of 5")
	if not reasons or incident.get("status") == "Closed":
		return []
	kind = incident.get("incident_type") or "Incident"
	where = f" on {incident['machine']}" if incident.get("machine") else ""
	return [
		{
			"rule_key": f"ehs-serious:{incident['name']}",
			"category": "Safety",
			"severity": "Critical",
			"title": f"Serious {kind.lower()} {incident['name']}{where}",
			"suggestion": (
				f"{kind} {incident['name']}{where} needs attention now: {'; '.join(reasons)}. Make the area safe, "
				"preserve the evidence, start the investigation"
				+ (
					", and check the notification deadline"
					if incident.get("reportable_release") or incident.get("osha_outcome") == "Death"
					else ""
				)
				+ "."
			),
			"reference_doctype": "Safety Incident",
			"reference_name": incident["name"],
			"evidence": {
				"incident_type": kind,
				"occurred_on": str(incident.get("occurred_on")),
				"recordable": bool(incident.get("recordable")),
				"osha_outcome": incident.get("osha_outcome"),
				"potential_severity": incident.get("potential_severity"),
				"reportable_release": bool(incident.get("reportable_release")),
			},
		}
	]
