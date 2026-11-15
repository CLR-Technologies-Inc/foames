# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read methods for NPI programs, PRDs, tech transfer packages and PD studies, and the scale-up
calculator, for the MCP server and external agents. Every method reads; none changes a record."""

from __future__ import annotations

import json

import frappe
from frappe.utils import cint, flt

from foames.foames_lifesci import npi, scaleup


def _program_status(doc) -> dict:
	rows = doc.deliverable_rows()
	gate = doc.gate(doc.current_stage)
	return {
		"name": doc.name,
		"title": doc.title,
		"product_name": doc.product_name,
		"product_type": doc.product_type,
		"program_lead": doc.program_lead,
		"current_stage": doc.current_stage,
		"status": doc.status,
		"next_gate": {
			"stage": gate.stage,
			"target_date": str(gate.target_date) if gate.target_date else None,
			"decision": gate.decision or None,
		},
		"current_stage_progress": npi.stage_progress(rows, doc.current_stage),
		"open_conditions": [
			{
				"stage": g.stage,
				"conditions": g.conditions,
				"due": str(g.conditions_due) if g.conditions_due else None,
			}
			for g in doc.gates
			if g.decision == "Conditional Go" and not g.conditions_closed
		],
		"decisions": [
			{
				"stage": g.stage,
				"decision": g.decision,
				"decided_by": g.decided_by,
				"decided_on": str(g.decided_on) if g.decided_on else None,
			}
			for g in doc.gates
			if g.decision
		],
		"product_requirements": doc.product_requirements,
		"tech_transfer_package": doc.tech_transfer_package,
	}


@frappe.whitelist()
def get_npi_status(program: str | None = None, include_closed: bool | int = False) -> list[dict]:
	"""Each NPI program's stage, status, next gate, required deliverables still open and open
	Conditional Go conditions."""
	frappe.has_permission("NPI Program", "read", throw=True)
	if program:
		names = [program]
	else:
		filters = {} if cint(include_closed) else {"status": ("in", ("Active", "On Hold"))}
		names = frappe.get_all(
			"NPI Program", filters=filters, pluck="name", order_by="modified desc", limit=200
		)
	out = []
	for name in names:
		doc = frappe.get_doc("NPI Program", name)
		doc.check_permission("read")
		out.append(_program_status(doc))
	return out


@frappe.whitelist()
def get_requirements_trace(document: str) -> dict:
	"""The trace matrix of a product requirements document: each requirement with its parent,
	children, design output, verification and validation, the gaps and the coverage figures."""
	doc = frappe.get_doc("Product Requirements Document", document)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"title": doc.title,
		"product_name": doc.product_name,
		"approved": doc.docstatus == 1,
		**doc.trace(),
	}


@frappe.whitelist()
def get_tech_transfer_package(package: str) -> dict:
	"""A tech transfer package: sites, scale, CPPs with NOR and PAR, CQAs with limits and
	approach, deliverables, open problems and the latest comparability outcome per attribute."""
	doc = frappe.get_doc("Tech Transfer Package", package)
	doc.check_permission("read")
	assessments = {}
	if frappe.has_permission("Comparability Assessment", "read"):
		for a in frappe.get_all(
			"Comparability Assessment",
			filters={"tech_transfer_package": package, "docstatus": ("<", 2)},
			fields=["name", "attribute", "outcome", "docstatus", "outcome_detail", "modified"],
			order_by="modified asc",
		):
			assessments[a.attribute] = {
				"name": a.name,
				"outcome": a.outcome,
				"reviewed": a.docstatus == 1,
				"detail": a.outcome_detail,
			}
	return {
		"name": doc.name,
		"title": doc.title,
		"product_name": doc.product_name,
		"process_name": doc.process_name,
		"transfer_type": doc.transfer_type,
		"sending_site": doc.sending_site,
		"receiving_site": doc.receiving_site,
		"scale": {
			"from": doc.from_scale,
			"to": doc.to_scale,
			"unit": doc.scale_uom,
			"ratio": doc.scale_ratio,
		},
		"approved": doc.docstatus == 1,
		"approved_by": doc.approved_by,
		"parameters": [
			{
				"parameter": p.parameter,
				"step": p.step,
				"unit": p.unit_of_measure,
				"criticality": p.criticality,
				"limits": p.limits,
				"set_point": p.set_point,
				"nor": [p.nor_low, p.nor_high],
				"par": [p.par_low, p.par_high],
				"scale_rule": p.scale_rule,
				"receiving_set_point": p.receiving_set_point,
			}
			for p in doc.parameters
		],
		"attributes": [
			{
				"attribute": a.attribute,
				"unit": a.unit_of_measure,
				"criticality": a.criticality,
				"limits": a.limits,
				"lower": a.lower,
				"upper": a.upper,
				"approach": a.approach,
				"requirement_id": a.requirement_id,
				"comparability": assessments.get(a.attribute),
			}
			for a in doc.attributes
		],
		"deliverables": [{"deliverable": d.deliverable, "status": d.status} for d in doc.deliverables],
		"problems": doc.problems() if doc.docstatus == 0 else [],
	}


@frappe.whitelist()
def get_pd_study(study: str) -> dict:
	"""A PD simulation study: factors, responses, runs, the fitted models and the last what-if."""
	doc = frappe.get_doc("PD Simulation Study", study)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"title": doc.title,
		"process_name": doc.process_name,
		"status": doc.status,
		"design": doc.design_type,
		"design_summary": doc.design_summary,
		"factors": doc.factor_specs(),
		"responses": doc.response_specs(),
		"runs": [
			{
				"run_no": r.run_no,
				"point_type": r.point_type,
				"excluded": bool(r.excluded),
				**{f.factor: r.get(f"x{i}") for i, f in enumerate(doc.factors, start=1)},
				**{resp.response: r.get(f"y{j}") or None for j, resp in enumerate(doc.responses, start=1)},
			}
			for r in doc.runs
		],
		"model_summary": doc.model_summary,
		"models": json.loads(doc.model_results)["models"] if doc.model_results else None,
		"what_if": json.loads(doc.what_if_results) if doc.what_if_results else None,
	}


@frappe.whitelist()
def scale_up(
	small_volume_l: float,
	large_volume_l: float,
	impeller_diameter_m: float,
	rpm: float,
	power_number: float = 5.0,
	density: float = 1000.0,
	viscosity: float = 0.001,
	tank_diameter_m: float | None = None,
	gas_l_min: float | None = None,
	gas_rule: str = "Constant vvm",
	kla_correlation: str = "Coalescing (van 't Riet)",
) -> dict:
	"""Stirred-vessel scale-up under geometric similarity: the large-scale speed, power per volume,
	tip speed, Reynolds number and kLa for each common criterion. Pure arithmetic; reads nothing."""
	try:
		return scaleup.scale_up(
			small_volume_l=flt(small_volume_l),
			large_volume_l=flt(large_volume_l),
			impeller_diameter_m=flt(impeller_diameter_m),
			rpm=flt(rpm),
			power_number=flt(power_number),
			density=flt(density),
			viscosity=flt(viscosity),
			tank_diameter_m=flt(tank_diameter_m) if tank_diameter_m not in (None, "") else None,
			gas_l_min=flt(gas_l_min) if gas_l_min not in (None, "") else None,
			gas_rule=gas_rule,
			kla_correlation=kla_correlation,
		)
	except ValueError as e:
		frappe.throw(str(e))
