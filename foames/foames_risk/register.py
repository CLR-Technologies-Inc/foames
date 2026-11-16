# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The site side of the risk register: settings, the records a risk may link to, the ratings read
from linked source assessments, the checks on control evidence, the scheduled check, and the
starting categories and templates.

A risk links to other FoaMES records instead of copying them. The record types it may link to are
the ones below that exist on the site, plus those other apps add with the hooks:

- ``foames_risk_linkable_doctypes``: a list of DocType names a risk may link to.
- ``foames_risk_source_readers``: {doctype: dotted path}. The function takes (doctype, name) and
  returns the linked record's current rating as one of risk.RATINGS, or None. A risk whose Source
  now rates higher than its own residual rating raises a suggestion.
- ``foames_risk_source_values``: {doctype: dotted path}. The function takes (doctype, name) and
  returns the fields for a new risk made from that record (title, category, risk_statement,
  inherent and residual ratings, machine).
- ``foames_risk_evidence_checks``: a list of dotted paths. Each takes (doctype, name) and returns a
  problem with that record as a short phrase ("is overdue"), or None.

The built-in readers and checks below look a record type up only when it is installed, so the
module works on a site without the EHS, PFMEA or work instruction modules, and picks them up when
they are added.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from foames.foames_risk.risk import DEFAULT_TOLERANCE, RATINGS, findings

DOCTYPE = "Enterprise Risk"
OPEN_STATUSES = ("Identified", "Assessed", "Treating", "Monitoring")

# Record types a risk may link to when they are installed.
DEFAULT_LINKABLE = (
	"Hazard Assessment",
	"Safety Incident",
	"Safety Permit",
	"Exposure Record",
	"PFMEA",
	"Work Instruction",
	"Standard Operating Procedure",
	"Maintenance Plan",
	"Maintenance Work Order",
	"Machine",
	"Downtime Record",
	"Andon Call",
	"Agent Suggestion",
	"Connector Write Policy",
	"Pending Write",
	"Enterprise Risk",
)

# The status a record must have for a control to rest on it.
EXPECTED_STATUS = {
	"Standard Operating Procedure": ("Effective",),
	"Work Instruction": ("Released",),
	"Hazard Assessment": ("Active",),
	"PFMEA": ("Released",),
}

# The EHS hazard assessment rates Low, Medium, High and Very High.
HAZARD_LEVELS = {"Low": "Low", "Medium": "Moderate", "High": "High", "Very High": "Very High"}


def settings() -> dict:
	s = frappe.get_cached_doc("Risk Settings")
	return {
		"risk_appetite": s.risk_appetite,
		"default_tolerance": s.default_tolerance or DEFAULT_TOLERANCE,
		"bands": {
			"Very Low": s.very_low_max,
			"Low": s.low_max,
			"Moderate": s.moderate_max,
			"High": s.high_max,
		},
		"review_days": s.review_days,
		"high_risk_review_days": s.high_risk_review_days,
		"verification_days": s.verification_days,
	}


def category_tolerance(category: str | None, values: dict | None = None) -> str:
	values = values or settings()
	tolerance = frappe.db.get_value("Risk Category", category, "tolerance") if category else None
	return tolerance or values.get("default_tolerance") or DEFAULT_TOLERANCE


def _installed(doctype: str) -> bool:
	return bool(doctype) and bool(frappe.db.exists("DocType", doctype))


def linkable_doctypes() -> list[str]:
	names = list(DEFAULT_LINKABLE) + list(frappe.get_hooks("foames_risk_linkable_doctypes") or [])
	return [d for d in dict.fromkeys(names) if _installed(d)]


def check_linkable(doctype: str, what: str):
	if doctype not in linkable_doctypes():
		frappe.throw(_("{0}: a risk cannot link to {1}").format(what, doctype or _("an empty type")))


def _hook_map(name: str) -> dict:
	merged = {}
	for key, value in (frappe.get_hooks(name) or {}).items():
		merged[key] = value[-1] if isinstance(value, list) else value
	return merged


def source_rating(doctype: str, name: str) -> str | None:
	"""The linked record's current rating on the register's scale, or None when it has none."""
	if not (_installed(doctype) and frappe.db.exists(doctype, name)):
		return None
	reader = _hook_map("foames_risk_source_readers").get(doctype)
	if reader:
		result = frappe.get_attr(reader)(doctype, name)
		return result if result in RATINGS else None
	if doctype == "Hazard Assessment":
		values = frappe.db.get_value(doctype, name, ["status", "risk_level", "residual_level"], as_dict=True)
		if values.status != "Active":
			return None
		return HAZARD_LEVELS.get(values.residual_level or values.risk_level)
	if doctype == "PFMEA":
		values = frappe.db.get_value(doctype, name, ["status", "high_count", "medium_count"], as_dict=True)
		if values.status != "Released":
			return None
		# Action priority High means the handbook asks for action; it is not a 5 x 5 rating, so it maps
		# to High at most, and to a floor the enterprise rating should not fall under.
		if values.high_count:
			return "High"
		return "Moderate" if values.medium_count else "Low"
	if doctype == "Enterprise Risk":
		return frappe.db.get_value(doctype, name, "residual_rating")
	return None


def source_values(doctype: str, name: str) -> dict:
	"""Fields for a new risk made from a source record."""
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} not found").format(doctype, name))
	maker = _hook_map("foames_risk_source_values").get(doctype)
	if maker:
		return frappe.get_attr(maker)(doctype, name)
	if doctype == "Hazard Assessment":
		h = frappe.get_doc(doctype, name)
		category = _first_category(("Safety and Health",))
		where = h.machine or h.location or h.task
		return {
			"title": h.title,
			"category": category,
			"machine": h.machine,
			"location": h.location,
			"risk_statement": _(
				"If the {0} hazard{1} is not controlled, then people may be harmed. Details: {2} {3}"
			).format(h.hazard_type or "", f" at {where}" if where else "", h.doctype, h.name),
			"inherent_impact": _clamp(h.severity),
			"inherent_likelihood": _clamp(h.likelihood),
			"residual_impact": _clamp(h.residual_severity) or None,
			"residual_likelihood": _clamp(h.residual_likelihood) or None,
			"response": "Reduce" if h.residual_severity or h.residual_likelihood else None,
			"current_actions": _("Controls are kept on {0} {1}").format(h.doctype, h.name),
		}
	if doctype == "PFMEA":
		p = frappe.get_doc(doctype, name)
		category = _first_category(("Product Quality",))
		high = int(p.high_count or 0)
		return {
			"title": _("Process failure modes: {0}").format(p.title),
			"category": category,
			"location": p.process_line,
			"risk_statement": _(
				"If the failure modes analysed in {0} {1} occur, then product may be defective, scrapped or "
				"recalled."
			).format(p.doctype, p.name),
			"inherent_impact": 4 if high else 3,
			"inherent_likelihood": 3,
			"current_actions": _("Failure modes and controls are kept on {0} {1}").format(p.doctype, p.name),
		}
	frappe.throw(_("FoaMES does not know how to make a risk from a {0}").format(doctype))


def _clamp(value) -> int | None:
	if not value:
		return None
	return max(1, min(5, int(value)))


def _first_category(preferred: tuple) -> str | None:
	for name in preferred:
		if frappe.db.exists("Risk Category", name):
			return name
	return frappe.db.get_value("Risk Category", {"disabled": 0}, "name", order_by="name asc")


def evidence_problem(doctype: str, name: str) -> str | None:
	"""Why a control's evidence record no longer supports it, or None."""
	if not _installed(doctype):
		return None
	if not frappe.db.exists(doctype, name):
		return "no longer exists"
	for path in frappe.get_hooks("foames_risk_evidence_checks") or []:
		problem = frappe.get_attr(path)(doctype, name)
		if problem:
			return problem
	if doctype in EXPECTED_STATUS:
		status = frappe.db.get_value(doctype, name, "status")
		if status not in EXPECTED_STATUS[doctype]:
			return f"is {status or 'without a status'}, not {' or '.join(EXPECTED_STATUS[doctype])}"
	if doctype == "Maintenance Plan":
		values = frappe.db.get_value(doctype, name, ["status", "disabled"], as_dict=True)
		if values.disabled:
			return "is disabled"
		if values.status == "Overdue":
			return "is overdue"
	if doctype == "Connector Write Policy" and not frappe.db.get_value(doctype, name, "read_only"):
		return "no longer keeps its connector read-only"
	return None


def rule_input(doc) -> dict:
	"""The values the pure findings rules read, from a saved risk."""
	apply_hierarchy = bool(frappe.db.get_value("Risk Category", doc.category, "apply_hierarchy"))
	evidence_issues = []
	for c in doc.controls:
		if c.status == "In Place" and c.evidence_doctype and c.evidence_name:
			problem = evidence_problem(c.evidence_doctype, c.evidence_name)
			if problem:
				evidence_issues.append(
					{
						"control": c.control,
						"doctype": c.evidence_doctype,
						"name": c.evidence_name,
						"problem": problem,
					}
				)
	sources = []
	for link in doc.links:
		if link.relation == "Source":
			current = source_rating(link.link_doctype, link.link_name)
			if current != link.source_rating:
				frappe.db.set_value("Risk Link", link.name, "source_rating", current, update_modified=False)
			if current:
				sources.append({"doctype": link.link_doctype, "name": link.link_name, "rating": current})
	return {
		"name": doc.name,
		"title": doc.title,
		"residual_rating": doc.residual_rating,
		"residual_score": doc.residual_score,
		"tolerance": doc.tolerance,
		"within_tolerance": bool(doc.within_tolerance),
		"accepted": bool(doc.accepted_by) and doc.accepted_score == doc.residual_score,
		"next_review_on": getdate(doc.next_review_on) if doc.next_review_on else None,
		"apply_hierarchy": apply_hierarchy,
		"controls": [
			{
				"name": c.name,
				"control": c.control,
				"control_level": c.control_level,
				"status": c.status,
				"verification_result": c.verification_result,
				"effectiveness": c.effectiveness,
				"next_verification_on": getdate(c.next_verification_on) if c.next_verification_on else None,
			}
			for c in doc.controls
		],
		"indicators": [
			{
				"name": i.name,
				"indicator": i.indicator,
				"breached": bool(i.breached),
				"current_value": i.current_value,
				"threshold": i.threshold,
				"as_of": str(i.as_of) if i.as_of else None,
			}
			for i in doc.indicators
		],
		"target_date": getdate(doc.target_date) if doc.target_date else None,
		"target_score": doc.target_score,
		"evidence_issues": evidence_issues,
		"sources": sources,
	}


def collect_findings(today=None) -> list[dict]:
	today = getdate(today or nowdate())
	out = []
	for name in frappe.get_all(
		DOCTYPE, filters={"status": ("in", OPEN_STATUSES)}, pluck="name", order_by="name"
	):
		out.extend(findings(rule_input(frappe.get_doc(DOCTYPE, name)), today))
	return out


def check_risks(today=None) -> list[str]:
	"""Scheduled daily: raise an Agent Suggestion for each open risk that is above tolerance without
	acceptance, overdue for review, relying only on lower-order controls for a High hazard, has a
	control overdue for verification, failed or resting on evidence that no longer holds, a breached
	key risk indicator, a missed target, or a source that now rates higher. Returns the suggestions
	created or reopened; each condition is raised once until it is resolved."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	return raise_suggestions(collect_findings(today), agent="foames-risk")


def heat_map_rows(filters=None) -> list[dict]:
	filters = filters or {}
	conditions = {"status": ("in", OPEN_STATUSES)}
	if filters.get("category"):
		conditions["category"] = filters["category"]
	return frappe.get_list(
		DOCTYPE,
		filters=conditions,
		fields=[
			"name",
			"inherent_impact",
			"inherent_likelihood",
			"residual_impact",
			"residual_likelihood",
		],
	)


def create_defaults():
	"""The starting categories and templates, created once on install and by a patch. Existing records
	with the same names are left as they are."""
	from foames.foames_risk.templates import CATEGORIES, TEMPLATES

	for name, tolerance, hierarchy, description in CATEGORIES:
		if not frappe.db.exists("Risk Category", name):
			frappe.get_doc(
				{
					"doctype": "Risk Category",
					"category_name": name,
					"tolerance": tolerance,
					"apply_hierarchy": hierarchy,
					"description": description,
				}
			).insert(ignore_permissions=True)
	for tpl in TEMPLATES:
		if frappe.db.exists("Risk Template", tpl["title"]):
			continue
		frappe.get_doc(
			{
				"doctype": "Risk Template",
				**{k: v for k, v in tpl.items() if k != "controls"},
				"controls": [
					{
						"control": c,
						"control_level": level,
						"control_function": fn,
						"verification_method": method,
					}
					for c, level, fn, method in tpl["controls"]
				],
			}
		).insert(ignore_permissions=True)
