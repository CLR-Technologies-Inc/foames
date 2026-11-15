# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Enterprise risk management as pure logic: scores, ratings, tolerance, the hierarchy of controls,
control verification, reviews and the findings an overdue or out-of-tolerance risk raises. No Frappe
dependency.

The method is the public, established one that US federal agencies use under OMB Circular A-123 and
that the US Department of Energy's Enterprise Risk Management guidance (FY 2024) spells out for its
risk profiles:

- a risk is a potential event, written "If <event>, then <impacts>", linked to one objective
  (strategic, operations, reporting or compliance);
- impact and likelihood are each rated 1 to 5, and their product (1 to 25) is the score, first as
  inherent risk (before any action) and then as residual risk (after the current response);
- the residual rating is never higher than the inherent one, and with no action taken it equals it;
- the response is Accept, Avoid, Reduce, Transfer or Share, and Transfer and Share name who takes
  the risk on;
- the residual rating is compared with the risk tolerance set for the risk's category, inside the
  organization's risk appetite;
- a proposed response treats the residual risk further, and the risk is monitored and reviewed.

Controls follow the hierarchy of controls (NIOSH; also ISO 45001 clause 8.1.2): elimination,
substitution, engineering controls, administrative controls and work practices, then personal
protective equipment. Each control in place is verified on an interval and its effectiveness is
reviewed, so a residual rating that rests on a control nobody has checked shows up as a finding.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise

SCALE = (1, 2, 3, 4, 5)
IMPACT_LABELS = {1: "Very Low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very High"}
# The likelihood bands of the DOE guidance (Table 5), as chances of occurrence.
LIKELIHOOD_LABELS = {
	1: "Very Low (under 5%)",
	2: "Low (5% to 25%)",
	3: "Moderate (26% to 49%)",
	4: "High (50% to 74%)",
	5: "Very High (75% or more)",
}
RATINGS = ("Very Low", "Low", "Moderate", "High", "Very High")
RATING_RANK = {rating: rank for rank, rating in enumerate(RATINGS)}
# The highest score of each rating band but the last. Scores are products of two 1-5 ratings, so
# they take the values 1-6, 8, 9, 10, 12, 15, 16, 20 and 25.
DEFAULT_BANDS = {"Very Low": 3, "Low": 6, "Moderate": 12, "High": 16}

RESPONSES = ("Accept", "Avoid", "Reduce", "Transfer", "Share")
NEEDS_COUNTERPARTY = ("Transfer", "Share")
OBJECTIVES = ("Strategic", "Operations", "Reporting", "Compliance")
STATUSES = ("Identified", "Assessed", "Treating", "Monitoring", "Closed")

# The hierarchy of controls, most effective first. Work practices are administrative controls in the
# NIOSH hierarchy; they are listed on their own because many standards name them separately
# ("engineering and work practice controls"). Other Management Control covers controls on risks
# that are not physical hazards (contracts, insurance, segregation of duties, a second supplier).
CONTROL_LEVELS = (
	"Elimination",
	"Substitution",
	"Engineering Controls",
	"Administrative Controls",
	"Work Practices",
	"PPE",
	"Other Management Control",
)
LEVEL_RANK = {
	"Elimination": 1,
	"Substitution": 2,
	"Engineering Controls": 3,
	"Administrative Controls": 4,
	"Work Practices": 4,
	"Other Management Control": 4,
	"PPE": 5,
}
# Controls that depend on people doing the right thing every time.
LOWER_ORDER_LEVELS = ("Administrative Controls", "Work Practices", "PPE")
CONTROL_FUNCTIONS = ("Preventive", "Detective", "Corrective", "Contingency")
CONTROL_STATUSES = ("Planned", "In Place", "Retired")
VERIFICATION_RESULTS = ("Not Verified", "Pass", "Fail")
EFFECTIVENESS = ("Not Assessed", "Effective", "Partially Effective", "Ineffective")

DEFAULT_REVIEW_DAYS = 365
DEFAULT_HIGH_RISK_REVIEW_DAYS = 90
DEFAULT_VERIFICATION_DAYS = 180
DEFAULT_TOLERANCE = "Moderate"


def check_rating(value, label: str) -> int:
	"""A 1-5 rating as an int, or ValueError naming the field."""
	try:
		number = int(value)
	except (TypeError, ValueError):
		raise ValueError(f"{label} must be a whole number from 1 to 5") from None
	if number not in SCALE or float(value) != number:
		raise ValueError(f"{label} must be a whole number from 1 to 5")
	return number


def score(impact: int, likelihood: int) -> int:
	return check_rating(impact, "Impact") * check_rating(likelihood, "Likelihood")


def normalise_bands(bands: dict | None) -> dict:
	"""The band limits, defaults filled in, checked to rise strictly within 1-24."""
	merged = dict(DEFAULT_BANDS)
	for rating, limit in (bands or {}).items():
		if rating in DEFAULT_BANDS and limit not in (None, "", 0):
			merged[rating] = int(limit)
	limits = [merged[r] for r in RATINGS[:-1]]
	if not all(1 <= x <= 24 for x in limits) or any(a >= b for a, b in pairwise(limits)):
		raise ValueError("the rating band limits must rise strictly between 1 and 24")
	return merged


def rating(value: int, bands: dict | None = None) -> str:
	"""The rating band a 1-25 score falls in."""
	limits = normalise_bands(bands)
	for name in RATINGS[:-1]:
		if value <= limits[name]:
			return name
	return RATINGS[-1]


def rating_rank(name: str | None) -> int | None:
	return RATING_RANK.get(name) if name else None


def within_tolerance(residual_rating: str, tolerance: str | None) -> bool:
	"""True when the residual rating is at or below the tolerance."""
	tolerance = tolerance or DEFAULT_TOLERANCE
	return RATING_RANK[residual_rating] <= RATING_RANK[tolerance]


def strongest_control(controls: list[dict]) -> str | None:
	"""The most effective level among the controls that are in place and not known to fail."""
	levels = [c.get("control_level") for c in controls if counts_as_in_place(c)]
	levels = [lvl for lvl in levels if lvl in LEVEL_RANK]
	if not levels:
		return None
	return min(levels, key=lambda lvl: (LEVEL_RANK[lvl], CONTROL_LEVELS.index(lvl)))


def counts_as_in_place(control: dict) -> bool:
	"""In place, and neither its last verification failed nor was it found ineffective."""
	return (
		control.get("status") == "In Place"
		and control.get("verification_result") != "Fail"
		and control.get("effectiveness") != "Ineffective"
	)


def only_lower_order(controls: list[dict]) -> bool:
	"""True when the controls in place are all administrative, work practices or PPE (or none)."""
	levels = [c.get("control_level") for c in controls if counts_as_in_place(c)]
	return all(lvl in LOWER_ORDER_LEVELS for lvl in levels)


def next_due(last: date | None, start: date | None, days: int | None) -> date | None:
	"""`days` after the last time it was done, or after `start` when it never was."""
	base = last or start
	if not base or not days or days <= 0:
		return None
	return base + timedelta(days=int(days))


def review_interval(residual_rating: str, set_days: int | None, settings: dict | None = None) -> int:
	"""The review interval: the one set on the risk, else the settings' for its rating."""
	if set_days and int(set_days) > 0:
		return int(set_days)
	settings = settings or {}
	if RATING_RANK[residual_rating] >= RATING_RANK["High"]:
		return int(settings.get("high_risk_review_days") or DEFAULT_HIGH_RISK_REVIEW_DAYS)
	return int(settings.get("review_days") or DEFAULT_REVIEW_DAYS)


def assess(risk: dict, settings: dict | None = None) -> dict:
	"""Check one risk and work out its derived values.

	`risk` holds the editable fields: inherent_impact, inherent_likelihood, residual_impact,
	residual_likelihood (either may be empty: no action taken), response, transfer_to, controls
	(dicts with control_level, status, verification_result, effectiveness), proposed_response,
	target_impact, target_likelihood, tolerance, risk_statement.

	Returns {"errors": [...], "warnings": [...], **derived}. Derived values are filled in only as far
	as the ratings allow.
	"""
	settings = settings or {}
	bands = settings.get("bands")
	errors: list[str] = []
	warnings: list[str] = []
	out: dict = {}
	controls = risk.get("controls") or []

	try:
		inherent_impact = check_rating(risk.get("inherent_impact"), "Inherent impact")
		inherent_likelihood = check_rating(risk.get("inherent_likelihood"), "Inherent likelihood")
	except ValueError as e:
		return {"errors": [str(e)], "warnings": warnings}
	out["inherent_score"] = inherent_impact * inherent_likelihood
	out["inherent_rating"] = rating(out["inherent_score"], bands)

	response = risk.get("response") or None
	if response and response not in RESPONSES:
		errors.append(f"Unknown response {response}")
	if response in NEEDS_COUNTERPARTY and not (risk.get("transfer_to") or "").strip():
		errors.append(f"A {response} response needs the organization the risk goes to")

	in_place = [c for c in controls if counts_as_in_place(c)]
	residual_impact = risk.get("residual_impact") or inherent_impact
	residual_likelihood = risk.get("residual_likelihood") or inherent_likelihood
	try:
		residual_impact = check_rating(residual_impact, "Residual impact")
		residual_likelihood = check_rating(residual_likelihood, "Residual likelihood")
	except ValueError as e:
		errors.append(str(e))
		return {"errors": errors, "warnings": warnings, **out}
	if residual_impact > inherent_impact or residual_likelihood > inherent_likelihood:
		errors.append("The residual impact and likelihood cannot be higher than the inherent ones")
	reduced = (residual_impact, residual_likelihood) != (inherent_impact, inherent_likelihood)
	if reduced and response == "Accept":
		errors.append(
			"An Accept response takes no action, so the residual rating must equal the inherent one"
		)
	if reduced and response in ("Reduce", None, "") and not in_place:
		errors.append(
			"A residual rating below the inherent one needs at least one control in place "
			"that has not failed verification"
		)
	out["residual_impact"] = residual_impact
	out["residual_likelihood"] = residual_likelihood
	out["residual_score"] = residual_impact * residual_likelihood
	out["residual_rating"] = rating(out["residual_score"], bands)

	tolerance = risk.get("tolerance") or settings.get("default_tolerance") or DEFAULT_TOLERANCE
	out["tolerance"] = tolerance
	out["within_tolerance"] = within_tolerance(out["residual_rating"], tolerance)
	out["strongest_control"] = strongest_control(controls)
	out["controls_in_place"] = len(in_place)

	proposed = risk.get("proposed_response") or None
	if proposed and proposed not in RESPONSES:
		errors.append(f"Unknown proposed response {proposed}")
	if risk.get("target_impact") or risk.get("target_likelihood"):
		try:
			target_impact = check_rating(risk.get("target_impact") or residual_impact, "Target impact")
			target_likelihood = check_rating(
				risk.get("target_likelihood") or residual_likelihood, "Target likelihood"
			)
		except ValueError as e:
			errors.append(str(e))
		else:
			if target_impact > residual_impact or target_likelihood > residual_likelihood:
				errors.append("The target impact and likelihood cannot be higher than the residual ones")
			out["target_impact"] = target_impact
			out["target_likelihood"] = target_likelihood
			out["target_score"] = target_impact * target_likelihood
			out["target_rating"] = rating(out["target_score"], bands)

	statement = (risk.get("risk_statement") or "").strip().lower()
	if statement and not (statement.startswith("if ") and " then " in f" {statement} "):
		warnings.append('Write the risk statement as "If <event>, then <impacts>"')
	for c in controls:
		if c.get("control_level") and c["control_level"] not in LEVEL_RANK:
			errors.append(f"Unknown control level {c['control_level']}")
	return {"errors": errors, "warnings": warnings, **out}


def control_schedule(control: dict, today: date, default_days: int | None = None) -> dict:
	"""When an in-place control is next due for verification, and whether it is overdue."""
	days = control.get("verification_interval_days") or default_days or DEFAULT_VERIFICATION_DAYS
	start = control.get("implemented_on")
	due = next_due(control.get("verified_on"), start, days) if control.get("status") == "In Place" else None
	return {"next_verification_on": due, "overdue": bool(due and due < today)}


def heat_map(risks: list[dict], which: str = "residual") -> list[list[int]]:
	"""Counts on the 5 x 5 grid: rows are impact 5 down to 1, columns likelihood 1 to 5."""
	grid = [[0] * 5 for _ in range(5)]
	for r in risks:
		impact, likelihood = r.get(f"{which}_impact"), r.get(f"{which}_likelihood")
		if impact in SCALE and likelihood in SCALE:
			grid[5 - impact][likelihood - 1] += 1
	return grid


def rule_key(kind: str, name: str, extra: str = "") -> str:
	return f"risk:{kind}:{name}" + (f":{extra}" if extra else "")


def findings(risk: dict, today: date) -> list[dict]:
	"""Agent Suggestion findings for one open risk.

	`risk` holds name, title, residual_rating, within_tolerance, accepted (residual accepted by
	management at its current score), next_review_on, apply_hierarchy (the category is a hazard
	category), controls (with name, control, control_level, next_verification_on and the verification
	fields), indicators (name, indicator, breached, current_value, threshold), target_date,
	target_score, residual_score, and sources: [{doctype, name, rating}] read from linked records,
	plus evidence_issues: [{control, doctype, name, problem}] from control evidence.
	"""
	out = []
	name = risk["name"]
	title = risk.get("title") or name
	residual = risk.get("residual_rating") or "Moderate"
	high = RATING_RANK[residual] >= RATING_RANK["High"]
	base = {"category": "Other", "reference_doctype": "Enterprise Risk", "reference_name": name}

	def add(kind, severity, text, evidence, extra=""):
		out.append(
			{
				**base,
				"title": f"Risk {name}: {text}",
				"severity": severity,
				"suggestion": f"<p>{title}: {text}.</p>",
				"evidence": evidence,
				"rule_key": rule_key(kind, name, extra),
			}
		)

	if not risk.get("within_tolerance") and not risk.get("accepted"):
		add(
			"tolerance",
			"Critical" if residual == "Very High" else "Warning",
			f"residual risk {residual} is above the {risk.get('tolerance') or DEFAULT_TOLERANCE} tolerance "
			"and has not been accepted; treat it further or record management's acceptance",
			{"residual_rating": residual, "tolerance": risk.get("tolerance")},
		)
	due = risk.get("next_review_on")
	if due and due < today:
		add(
			"review",
			"Warning" if high else "Info",
			f"review was due on {due.isoformat()}",
			{"next_review_on": due.isoformat(), "residual_rating": residual},
		)
	controls = risk.get("controls") or []
	if risk.get("apply_hierarchy") and high and only_lower_order(controls):
		add(
			"hierarchy",
			"Warning",
			f"residual risk {residual} relies only on administrative controls, work practices or PPE; "
			"look for elimination, substitution or an engineering control",
			{"strongest_control": strongest_control(controls)},
		)
	for c in controls:
		if c.get("status") != "In Place":
			continue
		label = c.get("control") or c.get("control_level") or "control"
		cid = c.get("name") or label
		nxt = c.get("next_verification_on")
		if nxt and nxt < today:
			add(
				"verify",
				"Warning" if high else "Info",
				f"control '{label}' ({c.get('control_level')}) was due for verification on {nxt.isoformat()}",
				{"control": label, "next_verification_on": nxt.isoformat()},
				cid,
			)
		if c.get("verification_result") == "Fail" or c.get("effectiveness") == "Ineffective":
			add(
				"ineffective",
				"Critical" if high else "Warning",
				f"control '{label}' failed verification or was found ineffective; reassess the residual risk",
				{
					"control": label,
					"verification_result": c.get("verification_result"),
					"effectiveness": c.get("effectiveness"),
				},
				cid,
			)
	for issue in risk.get("evidence_issues") or []:
		add(
			"evidence",
			"Warning",
			f"control '{issue['control']}' rests on {issue['doctype']} {issue['name']}, which {issue['problem']}",
			issue,
			f"{issue['doctype']}:{issue['name']}",
		)
	for ind in risk.get("indicators") or []:
		if ind.get("breached"):
			label = ind.get("indicator") or "indicator"
			add(
				"indicator",
				"Warning",
				f"key risk indicator '{label}' is at {ind.get('current_value')} against a threshold of "
				f"{ind.get('threshold')}",
				{k: ind.get(k) for k in ("indicator", "current_value", "threshold", "as_of")},
				ind.get("name") or label,
			)
	target_date = risk.get("target_date")
	if (
		target_date
		and target_date < today
		and risk.get("target_score")
		and (risk.get("residual_score") or 0) > risk["target_score"]
	):
		add(
			"target",
			"Info",
			f"the proposed response was due by {target_date.isoformat()} and the residual score "
			f"{risk.get('residual_score')} is still above the target {risk['target_score']}",
			{"target_date": target_date.isoformat(), "target_score": risk["target_score"]},
		)
	for src in risk.get("sources") or []:
		src_rank = rating_rank(src.get("rating"))
		if src_rank is not None and src_rank > RATING_RANK[residual]:
			add(
				"source",
				"Warning",
				f"linked {src['doctype']} {src['name']} now rates {src['rating']}, above this risk's "
				f"residual {residual}; reassess",
				src,
				f"{src['doctype']}:{src['name']}",
			)
	return out


def indicator_breached(value, threshold, direction: str = "Above") -> bool:
	"""A key risk indicator breaches when its value is above (or below) the threshold."""
	if value in (None, "") or threshold in (None, ""):
		return False
	value, threshold = float(value), float(threshold)
	return value < threshold if direction == "Below" else value > threshold
