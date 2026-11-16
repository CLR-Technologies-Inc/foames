# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""New product introduction (NPI) run as a stage-gate program. No Frappe dependency.

A program moves through six stages, each closed by a gate review: Concept, Feasibility,
Development, Verification & Validation, Transfer, Launch. Each stage carries deliverables; a gate
can only be passed (Go or Conditional Go) when every required deliverable of its stage is Complete
or Not Applicable. The decision is a person's, recorded with who made it; this module only says
whether the record supports it and what it does to the program:

- Go: the program moves to the next stage (after the Launch gate it is Launched).
- Conditional Go: as Go, with conditions and a due date that are tracked until closed.
- Recycle: the program stays in the stage to redo work; the gate can be decided again.
- Hold: the program is On Hold in the stage; a later decision on the same gate resumes it.
- Kill: the program is Cancelled.

The stage-gate pattern is R. G. Cooper's (Winning at New Products); the deliverable templates
follow device design controls (ISO 13485:2016 section 7.3, 21 CFR 820, ISO 14971, IEC 62366-1) and
the pharmaceutical development and transfer life cycle (ICH Q8(R2), Q9(R1), Q10, Q12). They are a
starting point for a site's own procedure, not a statement of what a regulator requires.
"""

from __future__ import annotations

from datetime import date

STAGES = ("Concept", "Feasibility", "Development", "Verification & Validation", "Transfer", "Launch")
DECISIONS = ("Go", "Conditional Go", "Recycle", "Hold", "Kill")
PASSING = ("Go", "Conditional Go")
DONE_STATUSES = ("Complete", "Not Applicable")
DELIVERABLE_STATUSES = ("Not Started", "In Progress", "Complete", "Not Applicable")
PROGRAM_STATUSES = ("Active", "On Hold", "Launched", "Cancelled")
CLOSED_PROGRAM = ("Launched", "Cancelled")
DEVICE_TYPES = ("Medical Device", "Combination Product", "In Vitro Diagnostic")
DEFAULT_GATE_WARNING_DAYS = 14

# (stage, deliverable, required). Device programs get design-control deliverables; drug and
# biologic programs get the QbD and transfer deliverables. A combination product gets both.
DEVICE_TEMPLATE: tuple[tuple[str, str, bool], ...] = (
	("Concept", "Intended use and user needs", True),
	("Concept", "Design and development plan", True),
	("Concept", "Preliminary hazard analysis (ISO 14971)", True),
	("Concept", "Regulatory pathway assessment", True),
	("Feasibility", "Product requirements document (design inputs) approved", True),
	("Feasibility", "Feasibility prototypes and test summary", True),
	("Feasibility", "Design review 1", True),
	("Development", "Design outputs (drawings, specifications, software)", True),
	("Development", "Design for manufacture and assembly review", True),
	("Development", "Design FMEA and process FMEA", True),
	("Development", "Process development studies (DoE) for key processes", True),
	("Development", "Supplier selection for critical components", True),
	("Development", "Design review 2", True),
	("Verification & Validation", "Design verification complete against design inputs", True),
	("Verification & Validation", "Design validation and usability (IEC 62366-1)", True),
	("Verification & Validation", "Biocompatibility, sterilization and shelf-life evidence", False),
	("Verification & Validation", "Risk management report updated", True),
	("Verification & Validation", "Process validation master plan", True),
	("Transfer", "Design transfer: device master record / medical device file", True),
	("Transfer", "Equipment IQ, OQ and PQ", True),
	("Transfer", "Process validation (PPQ) runs", True),
	("Transfer", "Work instructions, SOPs and operator training", True),
	("Transfer", "Supplier qualification and incoming inspection", True),
	("Launch", "Commercial readiness review", True),
	("Launch", "Design history file complete", True),
	("Launch", "Post-market surveillance and complaint handling plan", True),
)
DRUG_TEMPLATE: tuple[tuple[str, str, bool], ...] = (
	("Concept", "Quality target product profile (QTPP)", True),
	("Concept", "Development plan and regulatory strategy", True),
	("Feasibility", "Critical quality attributes identified", True),
	("Feasibility", "Initial quality risk assessment (ICH Q9)", True),
	("Feasibility", "Product requirements document approved", True),
	("Development", "Process characterization studies (DoE)", True),
	("Development", "Scale-down model qualification", False),
	("Development", "Draft control strategy (CPPs, IPCs, specifications)", True),
	("Development", "Process FMEA", True),
	("Verification & Validation", "Analytical method validation (ICH Q2(R2), Q14)", True),
	("Verification & Validation", "Stability program started (ICH Q1)", True),
	("Verification & Validation", "Engineering or demonstration batches", True),
	("Verification & Validation", "Process validation master plan", True),
	("Transfer", "Tech transfer package approved", True),
	("Transfer", "Analytical method transfer", True),
	("Transfer", "Equipment and facility fit (gap analysis), IQ, OQ and PQ", True),
	("Transfer", "Process performance qualification (PPQ) batches", True),
	("Transfer", "Comparability assessment, sending to receiving site", True),
	("Transfer", "Master batch records, SOPs and training", True),
	("Launch", "Commercial readiness review", True),
	("Launch", "Continued process verification (CPV) plan", True),
	("Launch", "Established conditions and post-approval change plan (ICH Q12)", False),
)


def template_for(product_type: str | None) -> list[tuple[str, str, bool]]:
	"""Deliverables for a new program of this product type."""
	if product_type == "Combination Product":
		seen, rows = set(), []
		for stage in STAGES:
			for template in (DEVICE_TEMPLATE, DRUG_TEMPLATE):
				for row in template:
					if row[0] == stage and row[1] not in seen:
						seen.add(row[1])
						rows.append(row)
		return rows
	if product_type in DEVICE_TYPES:
		return list(DEVICE_TEMPLATE)
	return list(DRUG_TEMPLATE)


def stage_index(stage: str) -> int:
	if stage not in STAGES:
		raise ValueError(f"unknown stage {stage!r}")
	return STAGES.index(stage)


def next_stage(stage: str) -> str | None:
	i = stage_index(stage)
	return STAGES[i + 1] if i + 1 < len(STAGES) else None


def missing_deliverables(deliverables: list[dict], stage: str) -> list[str]:
	"""Required deliverables of the stage that are not Complete or Not Applicable."""
	return [
		d["deliverable"]
		for d in deliverables
		if d.get("stage") == stage and d.get("required") and d.get("status") not in DONE_STATUSES
	]


def stage_progress(deliverables: list[dict], stage: str) -> dict:
	rows = [d for d in deliverables if d.get("stage") == stage]
	done = [d for d in rows if d.get("status") in DONE_STATUSES]
	required = [d for d in rows if d.get("required")]
	return {
		"stage": stage,
		"deliverables": len(rows),
		"done": len(done),
		"required": len(required),
		"missing_required": missing_deliverables(deliverables, stage),
		"percent_done": round(100.0 * len(done) / len(rows), 1) if rows else 100.0,
	}


def decision_problems(
	*,
	program_status: str,
	current_stage: str,
	gate_stage: str,
	decision: str,
	deliverables: list[dict],
	conditions: str | None = None,
	conditions_due: date | None = None,
	decided_by: str | None = None,
	program_lead: str | None = None,
) -> list[str]:
	"""Every reason the record does not support this gate decision; empty when it does."""
	problems = []
	if decision not in DECISIONS:
		return [f"Unknown decision {decision!r}"]
	if program_status in CLOSED_PROGRAM:
		problems.append(f"The program is {program_status}; no further gate decisions")
	if gate_stage != current_stage:
		problems.append(f"Only the gate of the current stage ({current_stage}) can be decided")
	if decided_by and program_lead and decided_by == program_lead:
		problems.append("The program lead cannot decide their own gate; another reviewer records it")
	if decision in PASSING:
		missing = missing_deliverables(deliverables, gate_stage)
		if missing:
			problems.append("Required deliverables are not complete: " + "; ".join(missing))
	if decision == "Conditional Go":
		if not (conditions or "").strip():
			problems.append("A Conditional Go needs its conditions written down")
		if not conditions_due:
			problems.append("A Conditional Go needs a date the conditions are due")
	if decision in ("Recycle", "Hold", "Kill") and not (conditions or "").strip():
		problems.append(f"A {decision} decision needs a rationale")
	return problems


def apply_decision(current_stage: str, decision: str) -> tuple[str, str]:
	"""(stage, program status) after a decision on the current stage's gate."""
	if decision in PASSING:
		following = next_stage(current_stage)
		return (current_stage, "Launched") if following is None else (following, "Active")
	if decision == "Hold":
		return current_stage, "On Hold"
	if decision == "Kill":
		return current_stage, "Cancelled"
	return current_stage, "Active"


def gate_findings(
	program: dict,
	gates: list[dict],
	deliverables: list[dict],
	today: date,
	warning_days: int = DEFAULT_GATE_WARNING_DAYS,
) -> list[dict]:
	"""Suggestions for one program: the current gate overdue or near with required work missing,
	and Conditional Go conditions past their due date and not closed."""
	out = []
	if program.get("status") in CLOSED_PROGRAM:
		return out
	name = program["name"]
	stage = program.get("current_stage")
	gate = next(
		(g for g in gates if g.get("stage") == stage and g.get("decision") not in (*PASSING, "Kill")), None
	)
	if gate and gate.get("target_date") and program.get("status") == "Active":
		missing = missing_deliverables(deliverables, stage)
		days = (gate["target_date"] - today).days
		if days < 0 or (missing and days <= warning_days):
			out.append(
				{
					"rule_key": f"npi-gate:{name}:{stage}:{gate['target_date']}",
					"title": f"{name}: {stage} gate {'overdue' if days < 0 else f'due in {days} days'}",
					"category": "Other",
					"severity": "Warning" if days < 0 else "Info",
					"suggestion": (
						f"The {stage} gate of {program.get('title') or name} was due on {gate['target_date']}. "
						if days < 0
						else f"The {stage} gate of {program.get('title') or name} is due on {gate['target_date']}. "
					)
					+ (
						f"{len(missing)} required deliverable(s) are open: {'; '.join(missing)}."
						if missing
						else "All required deliverables are done; schedule the gate review."
					),
					"evidence": {"stage": stage, "target_date": str(gate["target_date"]), "missing": missing},
				}
			)
	for g in gates:
		if (
			g.get("decision") == "Conditional Go"
			and g.get("conditions_due")
			and not g.get("conditions_closed")
			and g["conditions_due"] < today
		):
			out.append(
				{
					"rule_key": f"npi-conditions:{name}:{g['stage']}:{g['conditions_due']}",
					"title": f"{name}: conditions of the {g['stage']} gate are past due",
					"category": "Other",
					"severity": "Warning",
					"suggestion": (
						f"The Conditional Go on the {g['stage']} gate was due to have its conditions closed by "
						f"{g['conditions_due']}: {g.get('conditions') or ''}"
					),
					"evidence": {"stage": g["stage"], "conditions_due": str(g["conditions_due"])},
				}
			)
	return out
