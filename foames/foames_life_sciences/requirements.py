# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Product requirements and their trace matrix. No Frappe dependency.

A product requirements document holds requirements at levels that refine one another:

- for a device: User Need, then Design Input (ISO 13485:2016 section 7.3.3, 21 CFR 820.30(c));
- for a drug or biologic: QTPP Element, then CQA (ICH Q8(R2));
- for either: Regulatory and Business requirements, which sit at the top level.

Each requirement may name a parent one level up. The trace matrix follows every requirement down to
its children, its design output, its verification (does the output meet the input?) and its
validation (does the product meet the user need?). The coverage figures say what an auditor would
ask first: which user needs have no design input, which inputs have no verification method or
acceptance criteria, and which verifications are missing or failed.
"""

from __future__ import annotations

import re

LEVELS = ("User Need", "Design Input", "QTPP Element", "CQA", "Regulatory", "Business")
TOP_LEVELS = ("User Need", "QTPP Element", "Regulatory", "Business")
# Which level a child may refine.
PARENT_LEVELS = {"Design Input": TOP_LEVELS, "CQA": TOP_LEVELS}
VERIFICATION_METHODS = ("Test", "Inspection", "Analysis", "Demonstration", "Clinical", "Usability")
VERIFICATION_STATUSES = ("Not Started", "Planned", "Passed", "Failed")
REQ_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,39}$")


def requirement_problems(rows: list[dict]) -> list[str]:
	"""Structural problems that stop the document saving: ids, levels and parent links."""
	problems = []
	ids: dict[str, dict] = {}
	for row in rows:
		rid = (row.get("req_id") or "").strip()
		if not REQ_ID.match(rid):
			problems.append(
				f"Row {row.get('idx', '?')}: requirement id {rid!r} must start with a letter and use letters, digits, '.', '_' or '-'"
			)
			continue
		if rid in ids:
			problems.append(f"Requirement id {rid} is used twice")
		ids[rid] = row
		if row.get("level") not in LEVELS:
			problems.append(f"{rid}: unknown level {row.get('level')!r}")
	for rid, row in ids.items():
		parent = (row.get("parent_req") or "").strip()
		level = row.get("level")
		if not parent:
			continue
		if parent == rid:
			problems.append(f"{rid} cannot be its own parent")
			continue
		if parent not in ids:
			problems.append(f"{rid}: parent {parent} is not in this document")
			continue
		if not isinstance(level, str) or level not in LEVELS:
			# The first pass already reported this malformed level.
			continue
		allowed = PARENT_LEVELS.get(level)
		if allowed is None:
			problems.append(f"{rid}: a {level} is a top-level requirement and takes no parent")
		elif ids[parent].get("level") not in allowed:
			problems.append(
				f"{rid}: a {level} refines a {' or '.join(allowed)}, not a {ids[parent].get('level')}"
			)
	return problems


def trace_matrix(rows: list[dict]) -> dict:
	"""The trace matrix and its coverage, from the requirement rows of one document."""
	by_id = {r["req_id"]: r for r in rows if r.get("req_id")}
	children: dict[str, list[str]] = {rid: [] for rid in by_id}
	for rid, r in by_id.items():
		parent = r.get("parent_req")
		if parent in children:
			children[parent].append(rid)
	matrix, gaps = [], []
	for rid, r in by_id.items():
		level = r.get("level")
		kids = children[rid]
		status = r.get("verification_status") or "Not Started"
		entry = {
			"req_id": rid,
			"level": level,
			"requirement": r.get("requirement"),
			"critical": bool(r.get("critical")),
			"parent": r.get("parent_req") or None,
			"children": kids,
			"design_output": r.get("design_output") or None,
			"verification_method": r.get("verification_method") or None,
			"verification_reference": r.get("verification_reference") or None,
			"verification_status": status,
			"validation_reference": r.get("validation_reference") or None,
			"risk_reference": r.get("risk_reference") or None,
			"gaps": [],
		}
		if level in ("User Need", "QTPP Element") and not kids:
			entry["gaps"].append("not refined into any design input or CQA")
		if level in ("User Need",) and not r.get("validation_reference"):
			entry["gaps"].append("no design validation recorded")
		if level in ("Design Input", "CQA", "Regulatory"):
			if not r.get("acceptance_criteria"):
				entry["gaps"].append("no acceptance criteria")
			if not r.get("verification_method"):
				entry["gaps"].append("no verification method")
			if level == "Design Input" and not r.get("design_output"):
				entry["gaps"].append("no design output")
			if status == "Failed":
				entry["gaps"].append("verification failed")
			elif status != "Passed":
				entry["gaps"].append("not yet verified")
		if entry["gaps"]:
			gaps.append({"req_id": rid, "critical": entry["critical"], "gaps": entry["gaps"]})
		matrix.append(entry)
	verifiable = [m for m in matrix if m["level"] in ("Design Input", "CQA", "Regulatory")]
	passed = [m for m in verifiable if m["verification_status"] == "Passed"]
	failed = [m for m in verifiable if m["verification_status"] == "Failed"]
	tops = [m for m in matrix if m["level"] in ("User Need", "QTPP Element")]
	refined = [m for m in tops if m["children"]]
	return {
		"requirements": len(matrix),
		"verifiable": len(verifiable),
		"verified": len(passed),
		"failed": [m["req_id"] for m in failed],
		"critical_open": [g["req_id"] for g in gaps if g["critical"]],
		"percent_verified": round(100.0 * len(passed) / len(verifiable), 1) if verifiable else 100.0,
		"percent_refined": round(100.0 * len(refined) / len(tops), 1) if tops else 100.0,
		"gaps": gaps,
		"matrix": matrix,
	}
