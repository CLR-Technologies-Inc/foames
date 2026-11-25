# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Static, schema-aligned sample records for the coffee explorer.

Documents describe fictional assets and proposed workflows, not installed equipment,
importable fixtures, approved procedures or live Frappe records. Presentation metadata
stays outside the document fields. Measurements come from replay scenarios; the
espresso controller is a separately labelled synthetic teaching model.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from foames.foames_life_sciences.npi import STAGES as NPI_STAGES
from foames.foames_life_sciences.npi import stage_progress
from foames.foames_life_sciences.requirements import trace_matrix
from foames.foames_mes.work_instructions import evaluate_capture

STAGE_IDS = (
	"land",
	"nursery",
	"trellis",
	"cultivation",
	"harvest",
	"processing",
	"drying",
	"green",
	"roasting",
	"packaging",
	"brewing",
	"delivery",
)
SAMPLE_NOTE = (
	"Fictional static sample; no equipment is connected and no record has been created. "
	"Illustrations are original schematics, not OEM drawings, dimensions or verification of installed hardware."
)

# stage, silhouette, label, document type, equipment class
ASSET_SPECS = (
	("land", "land", "Teaching plot", "Facility Zone", "Outdoor"),
	("nursery", "nursery", "Propagation bench", "Facility Asset", "Propagation bench"),
	("trellis", "trellis", "Training posts and wires", "Facility Asset", "Plant support trellis"),
	("cultivation", "irrigation", "Irrigation manifold", "Facility Asset", "Irrigation manifold"),
	("harvest", "harvest", "Manual cherry receiving station", "Machine", "Manual receiving station"),
	("processing", "pulper", "Cherry pulper and wash station", "Machine", "Coffee pulper"),
	("drying", "dryer", "Parchment dryer", "Machine", "Coffee parchment dryer"),
	("green", "huller", "Huller and grading station", "Machine", "Coffee huller"),
	("roasting", "roaster", "Drum roaster and cooling tray", "Machine", "Coffee drum roaster"),
	("packaging", "packager", "Weigh-fill and seal station", "Machine", "Coffee bag packager"),
	("brewing", "grinder", "Cafe grinder", "Machine", "Coffee grinder"),
	("brewing", "brewer", "Filter brewer", "Machine", "Filter coffee brewer"),
	("brewing", "espresso", "Gaggia Classic Pro · CLR PID", "Machine", "Espresso machine with custom PID"),
	("delivery", "handoff", "Manual cup handoff station", "Machine", "Manual handoff station"),
)

# Same stage and asset identities support each view; these are explanatory lenses.
STAGE_VIEWS = {
	"land": {
		"supply": ["The plot anchors provenance; one hectare is a scenario assumption."],
		"manufacturing": ["A human reviews the plot before nursery material is assigned."],
		"engineering": ["Model land as a Facility Zone. Soil and climate measurements are not supplied."],
	},
	"nursery": {
		"supply": ["1,200 seeds become 1,000 released seedlings and 200 rejects."],
		"manufacturing": ["Record cohort identity and a manual selection check; plant counts are not mass."],
		"engineering": [
			"The bench is a Facility Asset; no automated growth or climate controller is simulated."
		],
	},
	"trellis": {
		"supply": ["The planted row retains both plot and nursery-cohort parents."],
		"manufacturing": ["Manual training and inspection are recorded over years, not playback seconds."],
		"engineering": [
			"Kona Joe-inspired cultivation choice; independent evidence is pending and assumed uplift is zero."
		],
	},
	"cultivation": {
		"supply": ["Scouting evidence follows the same row into the harvest lot."],
		"manufacturing": ["A person records field observations; this demo issues no treatment instructions."],
		"engineering": [
			"The irrigation manifold maps to Process Water. No water meter or weather service is connected."
		],
	},
	"harvest": {
		"supply": ["The receiving record identifies a 1,000 kg cherry lot and its row."],
		"manufacturing": ["Manual receiving and weighing are represented honestly as a station."],
		"engineering": ["A real deployment would verify scale calibration and safe material handling."],
	},
	"processing": {
		"supply": ["1,000 kg cherry becomes 420 kg wet parchment and 580 kg separated pulp/liquid."],
		"manufacturing": [
			"Pulper and wash station retain the lot ID; added wash water is outside this simplified balance."
		],
		"engineering": [
			"Guarding, cleaning isolation and wastewater collection need site-specific commissioning checks."
		],
	},
	"drying": {
		"supply": ["420 kg wet parchment becomes 210 kg dry parchment. A moisture failure holds that lot."],
		"manufacturing": [
			"The fictional 10-12% moisture band is a teaching limit, not a universal coffee specification."
		],
		"engineering": [
			"Dryer and moisture meter need local calibration and safety checks; no temperature recipe is prescribed."
		],
	},
	"green": {
		"supply": ["210 kg dry parchment becomes 170 kg green coffee and 40 kg parchment/grading rejects."],
		"manufacturing": [
			"Hulling follows release of dry parchment; the held scenario never reaches this stage."
		],
		"engineering": [
			"Inspect guards and dust extraction before use; sample records do not certify equipment."
		],
	},
	"roasting": {
		"supply": [
			"A 170 kg green lot loses 5 kg in sorting; a 165 kg charge yields 138.6 kg roasted coffee."
		],
		"manufacturing": [
			"Cooling and human quality review precede packing. There is no measured roast profile."
		],
		"engineering": [
			"Drum, exhaust and cooling tray are schematic; combustion and fire checks belong to the site's procedures."
		],
	},
	"packaging": {
		"supply": [
			"Pack identity continues through cafe receipt. A signal gap leaves 25 kg unfilled inventory."
		],
		"manufacturing": [
			"OEE uses the actual replay's 90-minute ledger, observed counter differences and six-second ideal cycle."
		],
		"engineering": [
			"Missing telemetry stays Unknown. A counter baseline is not production and a trend is not interpolation."
		],
	},
	"brewing": {
		"supply": [
			"A 250 g bag supplies an 18 g dose and retains 232 g. Filter and espresso routes have separate cup records."
		],
		"manufacturing": [
			"The selected scenario defines the beverage, water input and remaining material. A brew is not a handoff."
		],
		"engineering": [
			"The grinder, filter brewer and custom PID espresso machine are separate sample Machines. The PID uses a synthetic thermal model."
		],
	},
	"delivery": {
		"supply": ["An explicit handoff links the order and cup; recall review retains that history."],
		"manufacturing": ["A person records the handoff. Brewing alone never means delivered."],
		"engineering": ["This is a manual station with no physical actuator or automatic customer action."],
	},
}


def _asset_id(stage, kind):
	return f"DEMO-ASSET-{kind.upper() if stage == 'brewing' else stage.upper()}"


def _metric(scenario, stage, label):
	return next((m["value"] for m in scenario["stages"][stage]["metrics"] if m["label"] == label), None)


def _uses_asset(scenario, kind):
	if kind == "espresso":
		return bool(scenario.get("espresso"))
	return kind != "brewer" or not scenario.get("espresso")


def _pid_signals(scenarios):
	result = []
	for field, label, unit in (
		("temperature_c", "Model temperature", "°C"),
		("setpoint_c", "Model setpoint", "°C"),
		("heater_percent", "Model heater output", "%"),
		("beverage_g", "Model cup fill", "g"),
	):
		result.append(
			{
				"id": f"espresso-{field}",
				"label": label,
				"unit": unit,
				"kind": "time",
				"origin": "synthetic-pid-model",
				"x_axis": "Model sample time (HST)",
				"y_axis": f"{label} ({unit})",
				"interpolation": "none",
				"scenarios": {
					scenario["id"]: [
						{"time": sample["time"], "value": sample[field]}
						for sample in scenario.get("espresso", {}).get("samples", [])
					]
					for scenario in scenarios
				},
				"source_note": "Synthetic PID teaching model at one-second steps; not Gaggia measurements, calibrated thermal dynamics, or hardware tuning settings. Cup fill follows an assumed flow, not the thermal controller output.",
			}
		)
	return result


def _signals(stage, kind, scenarios):
	"""Only replay observations; single measurements remain single points."""
	specs = {
		"land": [("Area", "ha")],
		"nursery": [("Released seedlings", "plants")],
		"trellis": [],
		"cultivation": [],
		"harvest": [("Cherry received", "kg")],
		"processing": [("Wet parchment", "kg")],
		"drying": [("Moisture sample", "%"), ("Dry parchment", "kg")],
		"green": [("Green coffee", "kg")],
		"roasting": [("Roasted output", "kg")],
		"packaging": [],
		"brewing": [("Dose", "g")] if kind == "grinder" else [("TDS", "%"), ("Extraction", "%")],
		"delivery": [],
	}
	result = []
	for label, unit in () if kind == "espresso" else specs[stage]:
		values = {}
		for scenario in scenarios:
			record = scenario["stages"][stage]
			value = _metric(scenario, stage, label) if _uses_asset(scenario, kind) else None
			values[scenario["id"]] = (
				[] if record["time"] is None or value is None else [{"time": record["time"], "value": value}]
			)
		result.append(
			{
				"id": f"{kind}-{label.lower().replace(' ', '-')}",
				"label": label,
				"unit": unit,
				"source_note": "One fictional replay observation, not continuous telemetry. No interpolation.",
				"scenarios": values,
			}
		)
	if stage == "packaging":
		for counter in ("good", "scrap"):
			values = {}
			for scenario in scenarios:
				end = scenario["stages"][stage]["time"]
				points = []
				if end:
					end_time = datetime.fromisoformat(end)
					start = end_time - timedelta(minutes=scenario["oee"]["ledger"]["planned_minutes"])
					readings = scenario["counter_readings"][counter]
					points.append({"time": start.isoformat(), "value": readings[0]})
					if scenario["oee"]["ledger"]["unknown_minutes"]:
						points.append({"time": (end_time - timedelta(minutes=5)).isoformat(), "value": None})
					points.append({"time": end, "value": readings[-1]})
				values[scenario["id"]] = points
			result.append(
				{
					"id": f"packager-{counter}-counter",
					"label": f"{counter.title()} running counter",
					"unit": "bags",
					"source_note": "Replay baseline and final reading at the packaging-window boundaries. A null marks the missing signal; its position is illustrative, not a timestamped outage log. Only the endpoint difference counts as production.",
					"scenarios": values,
				}
			)
	for signal in result:
		signal.update(
			kind="time",
			x_axis="Observation time (HST)",
			y_axis=f"{signal['label']} ({signal['unit']})",
			interpolation="none",
		)
	if kind == "espresso":
		result.extend(_pid_signals(scenarios))
	if any(b["stage"] == stage for scenario in scenarios for b in scenario["mass_balance"]):
		values = {}
		notes = {}
		for scenario in scenarios:
			balance = next(
				(b for b in scenario["mass_balance"] if b["stage"] == stage and _uses_asset(scenario, kind)),
				None,
			)
			values[scenario["id"]] = (
				[]
				if balance is None
				else [
					{"time": "Input", "value": balance["input_kg"]},
					{"time": "Product", "value": balance["output_kg"]},
					{"time": "Other", "value": balance["other_kg"]},
				]
			)
			notes[scenario["id"]] = None if balance is None else balance["other_label"]
		result.append(
			{
				"id": f"{kind}-stage-mass-balance",
				"label": "Stage mass balance",
				"unit": "kg",
				"kind": "categorical",
				"x_axis": "Stage mass-balance category",
				"y_axis": "Mass (kg)",
				"interpolation": "none",
				"scenarios": values,
				"scenario_notes": notes,
				"source_note": "Whole-stage material balance, not individual machine telemetry or a time trend. Input = Product + Other. Roasting includes pre-roast sorting; the brewing balance covers the combined grinder/brewer stage and added water. See the scenario note for the other stream.",
			}
		)
	return result


def _source_definition(doctype):
	module = {
		"Facility Zone": "foames_bms",
		"Facility Asset": "foames_bms",
		"Machine": "foames_mes",
		"Work Instruction": "foames_mes",
		"NPI Program": "foames_life_sciences",
		"Product Requirements Document": "foames_life_sciences",
		"Tech Transfer Package": "foames_life_sciences",
		"Validation Protocol": "foames_validation",
	}[doctype]
	name = doctype.lower().replace(" ", "_")
	return f"foames/{module}/doctype/{name}/{name}.json"


def _assets(scenarios):
	assets = []
	for stage, kind, label, doctype, equipment_class in ASSET_SPECS:
		identity = _asset_id(stage, kind)
		document = {"doctype": doctype, "name": identity}
		if doctype == "Facility Zone":
			document.update(
				zone_name=identity, zone_type="Outdoor", description="Fictional coffee teaching plot"
			)
		elif doctype == "Facility Asset":
			document.update(
				asset_name=identity,
				title=label,
				equipment_class=equipment_class,
				system="Process Water" if kind == "irrigation" else "Other",
				zone="DEMO-ASSET-LAND",
				status="Unknown",
				notes=SAMPLE_NOTE,
			)
		else:
			document.update(
				code=identity,
				title=label,
				machine_type=equipment_class,
				line="DEMO-COFFEE",
				status="Unknown",
				source_id=f"demo-coffee-{kind}",
			)
			if kind == "packager":
				document["ideal_cycle_seconds"] = 6
		assets.append(
			{
				"id": identity,
				"name": identity,
				"label": label,
				"doctype": doctype,
				"stage_ids": [stage],
				"kind": kind,
				"silhouette": kind,
				"description": SAMPLE_NOTE,
				"document": document,
				"source_definition": _source_definition(doctype),
				**STAGE_VIEWS[stage],
				"signals": _signals(stage, kind, scenarios),
				"work_instruction_ids": [f"DEMO-WI-{stage.upper()}"],
			}
		)
		if kind == "espresso":
			assets[-1].update(
				description="Gaggia Classic Pro RI9380 form, with a fictional custom PID retrofit and CLR blue/olive powder-coated case. Original schematic illustration; not an OEM finish, measured machine or live connection.",
				supply=[
					"The espresso route links an 18 g dose to its own 36 g cup and explicit cafe handoff."
				],
				manufacturing=[
					"Replay a synthetic brew and review cup mass, dose and extraction in the linked draft instructions."
				],
				engineering=[
					"A proportional-integral-derivative teaching loop regulates a simplified temperature model; heater output is clamped to 0-100%. No machine command is sent."
				],
				work_instruction_ids=["DEMO-WI-BREWING", "DEMO-WI-ESPRESSO"],
				finish={"body": "#3683A4", "accent": "#A2A342", "type": "CLR powder-coat concept"},
				source_ids=["gaggia-classic-pro-manual", "gaggia-pid-retrofit", "clr-palette"],
			)
	return assets


# A numeric check is a teaching example, never an instruction to operate real equipment.
CHECKS = {
	"land": ("Review plot boundary", "Area", "ha", None, None),
	"nursery": ("Count selected seedlings", "Released seedlings", "plants", None, None),
	"trellis": ("Inspect supports and plant identity", None, "", None, None),
	"cultivation": ("Review scouting record", None, "", None, None),
	"harvest": ("Record received cherry mass", "Cherry received", "kg", None, None),
	"processing": ("Record wet parchment output", "Wet parchment", "kg", None, None),
	"drying": ("Measure parchment moisture", "Moisture sample", "%", 10, 12),
	"green": ("Record graded green mass", "Green coffee", "kg", None, None),
	"roasting": ("Record cooled output mass", "Roasted output", "kg", None, None),
	"packaging": ("Reconcile released bag count", "Released packages", "bags", None, None),
	"brewing": ("Calculate extraction from dose, beverage and TDS", "Extraction", "%", 18, 22),
	"delivery": ("Record explicit handoff", None, "", None, None),
}
STEP_INSTRUCTIONS = {
	"land": "Compare the plot identity and boundary to the local land-use and soil review; record reviewed area.",
	"nursery": "Keep seed-lot identity, count selected seedlings and separately record rejects.",
	"trellis": "Confirm row and nursery-cohort identity; inspect supports using a locally approved method. Record defects for human review.",
	"cultivation": "Record observed plant conditions and inspection date. Escalate exceptions without issuing treatment commands.",
	"harvest": "Confirm the receiving scale's verification status, identify the row and record cherry mass.",
	"processing": "Confirm lot identity and cleaning status under the site's procedure, then record wet parchment and separated material.",
	"drying": "Use the site's sampling and moisture-meter method. Record the sample; retain the lot on hold when outside the demo band.",
	"green": "Confirm upstream release before hulling; record green coffee and grading rejects separately.",
	"roasting": "Confirm incoming lot and local operating authorization; record charge, cooled output and review evidence. No roast settings are supplied.",
	"packaging": "Record baseline and final counters; reconcile good bags, rejects, retained sample and unfilled inventory. Never estimate missing output.",
	"brewing": "Record the identified bag, dose, water, beverage and TDS. Calculate extraction as beverage mass times TDS fraction divided by dose.",
	"delivery": "Match the order to the cup and explicitly record the handoff. Do not infer it from elapsed time.",
}


def _work_instructions(assets, scenarios):
	instructions = []
	for stage in STAGE_IDS:
		identity = f"DEMO-WI-{stage.upper()}"
		title, metric, unit, lower, upper = CHECKS[stage]
		scoped = [a for a in assets if stage in a["stage_ids"]]
		capture = "Number" if metric else "Pass/Fail"
		check = {
			"doctype": "Work Instruction Step",
			"title": title,
			"capture": capture,
			"instruction": STEP_INSTRUCTIONS[stage],
			"unit": unit,
			"stop_on_fail": 1,
			"sign_off_role": "FoaMES Quality",
			"post_measurement": 0,
		}
		if lower is not None:
			check.update(has_lower_limit=1, lower_limit=lower, has_upper_limit=1, upper_limit=upper)
		steps = [
			{
				"doctype": "Work Instruction Step",
				"title": "Identify the material and station",
				"capture": "Text",
				"instruction": "Record the source lot or plot identity and verify it against the traveler.",
			},
			check,
			{
				"doctype": "Work Instruction Step",
				"title": "Record disposition and evidence",
				"capture": "Confirm",
				"instruction": "Attach the local check evidence. A human resolves any hold before downstream work begins.",
			},
		]
		document = {
			"doctype": "Work Instruction",
			"name": identity,
			"instruction_code": identity,
			"title": title,
			"revision": 1,
			"status": "Draft",
			"operation": stage,
			"steps": steps,
			"description": "Illustrative draft template, not an approved operating procedure or executed run.",
			"safety_notes": "Use locally approved safety, isolation, hygiene and equipment procedures; these examples are incomplete for operation.",
		}
		if len(scoped) == 1 and scoped[0]["doctype"] == "Machine":
			document["machine"] = scoped[0]["name"]
		acceptance = (
			f"Fictional inclusive band: {lower}-{upper} {unit}. Human review and second-person sign-off required."
			if lower is not None
			else "Record the observed value or explicit check; no numerical release specification is inferred."
		)
		evaluations = {}
		for scenario in scenarios:
			stage_record = scenario["stages"][stage]
			value = _metric(scenario, stage, metric) if metric else "Pass"
			evaluations[scenario["id"]] = (
				None
				if stage_record["time"] is None
				else {
					**evaluate_capture(check, value),
					"record_id": stage_record["record_id"],
					"note": "Pure-rule illustration only; no Work Instruction Run or sign-off was created.",
				}
			)
		instructions.append(
			{
				"id": identity,
				"title": title,
				"stage_ids": [stage],
				"asset_ids": [a["id"] for a in scoped],
				"revision": 1,
				"status": "Draft",
				"document": document,
				"sample_evaluations": evaluations,
				"source_definition": _source_definition("Work Instruction"),
				"steps": [
					{
						"title": s["title"],
						"instruction": s["instruction"],
						"document": s,
						"acceptance": acceptance
						if i == 1
						else "Required record; this sample has no execution or approval.",
						"evidence": "Fictional replay record; real attachments, operator identity and reviewer sign-off are not provided.",
					}
					for i, s in enumerate(steps)
				],
			}
		)
	instructions.append(_espresso_instruction(scenarios))
	return instructions


def _espresso_instruction(scenarios):
	identity = "DEMO-WI-ESPRESSO"
	title = "Review the PID espresso sample"
	steps = [
		{
			"doctype": "Work Instruction Step",
			"title": "Identify the espresso route",
			"capture": "Text",
			"instruction": "Link the cafe receipt, espresso brew and order. Confirm the selected machine is DEMO-ASSET-ESPRESSO.",
		},
		{
			"doctype": "Work Instruction Step",
			"title": "Review controller evidence and cup mass",
			"capture": "Number",
			"unit": "g",
			"stop_on_fail": 1,
			"post_measurement": 0,
			"instruction": "Compare model temperature, setpoint and bounded heater output through the simulated brew. Record final cup mass. This replay does not validate a real PID or supply tuning settings.",
		},
		{
			"doctype": "Work Instruction Step",
			"title": "Review the separate handoff",
			"capture": "Confirm",
			"instruction": "Check the explicit handoff record and its timestamp. Playback completion and cup fill do not create a delivery or approval.",
		},
	]
	return {
		"id": identity,
		"title": title,
		"stage_ids": ["brewing"],
		"asset_ids": ["DEMO-ASSET-ESPRESSO"],
		"revision": 1,
		"status": "Draft",
		"document": {
			"doctype": "Work Instruction",
			"name": identity,
			"instruction_code": identity,
			"title": title,
			"revision": 1,
			"status": "Draft",
			"operation": "brewing",
			"machine": "DEMO-ASSET-ESPRESSO",
			"steps": steps,
			"description": "Draft review of a fictional espresso replay; not an approved machine operating procedure.",
			"safety_notes": "No wiring, retrofit, coating, calibration or physical operating procedure is supplied.",
		},
		"sample_evaluations": {
			scenario["id"]: {
				**evaluate_capture(steps[1], scenario["espresso"]["yield_g"]),
				"record_id": scenario["stages"]["brewing"]["record_id"],
				"note": "Numeric capture rule only; no release specification, execution or sign-off is inferred.",
			}
			if scenario.get("espresso")
			else None
			for scenario in scenarios
		},
		"source_definition": _source_definition("Work Instruction"),
		"steps": [
			{
				"title": step["title"],
				"instruction": step["instruction"],
				"document": step,
				"acceptance": "Record the evidence for review. The 36 g cup is a scenario assumption, not a general brew specification.",
				"evidence": "Synthetic model and fictional trace records only; real operator and reviewer evidence are not supplied.",
			}
			for step in steps
		],
	}


def _npi(assets):
	"""Coffee-specific proposals avoid the default pharmaceutical template for Other."""
	routes = (
		(
			"Concept",
			["land", "nursery"],
			"Define the Arabica candidate, intended cup and provenance requirements",
		),
		(
			"Feasibility",
			["trellis", "cultivation", "harvest"],
			"Review cultivar suitability and an evidence plan for cultivation alternatives",
		),
		(
			"Development",
			["processing", "drying", "green", "roasting"],
			"Design a pilot route, risk review and draft process checks",
		),
		(
			"Verification & Validation",
			["drying", "roasting", "brewing"],
			"Plan moisture, identity and sensory verification against the product requirements",
		),
		(
			"Transfer",
			["processing", "drying", "green", "roasting", "packaging", "brewing"],
			"Review equipment fit, work instructions and pilot-to-line transfer",
		),
		(
			"Launch",
			["packaging", "brewing", "delivery"],
			"Review package traceability, handoff and recall readiness before authorizing launch",
		),
	)
	program_id, requirements_id, transfer_id = "DEMO-NPI-ARABICA", "DEMO-PRD-ARABICA", "DEMO-TTP-ARABICA"
	deliverables = [
		{
			"doctype": "NPI Deliverable",
			"stage": stage,
			"deliverable": text,
			"required": 1,
			"status": "Not Started",
		}
		for stage, _, text in routes
	]
	criteria = [
		{
			"doctype": "NPI Phase Criterion",
			"stage": stage,
			"kind": "Exit",
			"criterion": text,
			"required": 1,
			"met": 0,
		}
		for stage, _, text in routes
	]
	program = {
		"doctype": "NPI Program",
		"name": program_id,
		"naming_series": "NPI-.YYYY.-",
		"title": "Proposed Arabica variety and product introduction",
		"product_name": "Fictional Arabica pilot coffee",
		"product_type": "Other",
		"program_lead": "demo.lead@example.invalid",
		"current_stage": "Concept",
		"status": "Active",
		"product_requirements": requirements_id,
		"tech_transfer_package": transfer_id,
		"description": "Proposed static shape only. Active is the schema's initial state, not a claim that a real program exists. The lead is a placeholder. No gates have been decided. Coffee-specific deliverables replace the default template; no pharmaceutical regulatory requirements are asserted.",
		"gates": [{"doctype": "NPI Gate", "stage": stage} for stage in NPI_STAGES],
		"deliverables": deliverables,
		"criteria": criteria,
	}
	requirements = {
		"doctype": "Product Requirements Document",
		"name": requirements_id,
		"naming_series": "REQ-.YYYY.-",
		"title": "Proposed Arabica product requirements",
		"product_name": program["product_name"],
		"product_type": "Other",
		"document_revision": "Draft 1",
		"npi_program": program_id,
		"intended_use": "A traceable pilot filter-coffee product; variety and sensory target remain to be selected.",
		"requirements": [
			{
				"doctype": "Product Requirement",
				"req_id": "AR-NEED-01",
				"level": "User Need",
				"requirement": "Trace the delivered cup to its proposed Arabica cohort and plot.",
				"verification_status": "Planned",
			},
			{
				"doctype": "Product Requirement",
				"req_id": "AR-TRACE-01",
				"level": "Design Input",
				"parent_req": "AR-NEED-01",
				"requirement": "Preserve material genealogy and explicit order handoff.",
				"acceptance_criteria": "Every pilot handoff resolves to a bag, roast, green lot, cherry lot, row, cohort and plot.",
				"design_output": "Proposed coffee traveler and lot map",
				"verification_method": "Demonstration",
				"verification_status": "Planned",
				"critical": 1,
			},
			{
				"doctype": "Product Requirement",
				"req_id": "AR-MOISTURE-01",
				"level": "Design Input",
				"parent_req": "AR-NEED-01",
				"requirement": "Hold dry parchment outside the agreed release band.",
				"acceptance_criteria": "Teaching assumption: 10-12% moisture; site review must establish the actual specification.",
				"design_output": "Proposed drying check",
				"verification_method": "Test",
				"verification_status": "Planned",
			},
			{
				"doctype": "Product Requirement",
				"req_id": "AR-CUP-01",
				"level": "Business",
				"requirement": "Agree a sensory target, cultivar choice and pilot economics before launch.",
				"acceptance_criteria": "Document a reviewed target and pilot evidence; neither is supplied by this replay.",
				"verification_method": "Inspection",
				"verification_status": "Not Started",
			},
		],
	}
	transfer = {
		"doctype": "Tech Transfer Package",
		"name": transfer_id,
		"naming_series": "TTP-.YYYY.-",
		"title": "Proposed Arabica pilot-to-line transfer",
		"product_name": program["product_name"],
		"process_name": "Coffee processing, roasting and packaging",
		"transfer_type": "Development to Commercial",
		"sending_site": "Fictional pilot station",
		"receiving_site": "Fictional coffee line",
		"npi_program": program_id,
		"product_requirements": requirements_id,
		"process_description": "Proposed route uses the same explorer assets. No batches or transfer approval have been executed.",
		"control_strategy": "Qualify local methods and equipment, retain lot identity, stop on failed release checks and require human review. Numerical proven acceptable ranges are not claimed.",
		"parameters": [
			{
				"doctype": "Tech Transfer Parameter",
				"parameter": "Pilot brew dose",
				"step": "brewing",
				"unit_of_measure": "g",
				"criticality": "Non-critical",
				"limits": "None",
				"set_point": 18,
				"justification": "Replay reference only; pilot operating ranges remain unestablished.",
			}
		],
		"attributes": [
			{
				"doctype": "Tech Transfer Attribute",
				"attribute": "Dry parchment moisture",
				"unit_of_measure": "%",
				"criticality": "CQA",
				"requirement_id": "AR-MOISTURE-01",
				"analytical_method": "Site moisture method to be selected and verified",
				"limits": "Lower and Upper",
				"lower": 10,
				"upper": 12,
				"approach": "Descriptive",
			}
		],
		"deliverables": [
			{
				"doctype": "NPI Deliverable",
				"stage": "Transfer",
				"deliverable": "Review actual operating limits, training and receiving equipment readiness",
				"required": 1,
				"status": "Not Started",
			}
		],
	}
	validation = {
		"doctype": "Validation Protocol",
		"name": "DEMO-VP-ARABICA-IQ",
		"naming_series": "VP-.YYYY.-",
		"title": "Optional proposed dryer installation-check protocol",
		"protocol_type": "IQ",
		"machine": "DEMO-ASSET-DRYING",
		"required_runs": 1,
		"enforce_sequence": 1,
		"objective": "Illustrate an optional organizational qualification workflow, not a legal requirement for coffee.",
		"scope": "Draft sample only; no approval, execution, certification or equipment qualification exists.",
		"criteria": [
			{
				"doctype": "Validation Acceptance Criterion",
				"criterion": "Verify dryer identity and installation evidence",
				"check_type": "Pass/Fail",
				"critical": 1,
				"evidence_required": 1,
				"source": "Manual",
				"method": "A competent reviewer checks the actual equipment against the site's approved installation checklist.",
			}
		],
	}
	return {
		"title": "Introduce an Arabica variety and product",
		"status": "Proposed",
		"summary": "A proposed flow on the same assets and twelve stages. Cultivar selection, local trials and sensory evidence remain open. No launch, approval or cultivation benefit is claimed.",
		"program": program,
		"requirements": requirements,
		"transfer": transfer,
		"validation": validation,
		"source_definitions": {
			key: _source_definition(doc["doctype"])
			for key, doc in (
				("program", program),
				("requirements", requirements),
				("transfer", transfer),
				("validation", validation),
			)
		},
		"requirement_coverage": trace_matrix(requirements["requirements"]),
		"gates": [
			{
				"id": f"arabica-gate-{i + 1}",
				"title": stage,
				"stage_ids": stage_ids,
				"asset_ids": [a["id"] for a in assets if set(a["stage_ids"]) & set(stage_ids)],
				"status": "Proposed — no decision",
				"deliverables": [text],
				"acceptance": "Required evidence is not started; a human gate review is still needed.",
				"progress": stage_progress(deliverables, stage),
			}
			for i, (stage, stage_ids, text) in enumerate(routes)
		],
	}


def _coverage(assets):
	rows = (
		(
			"Espresso PID replay",
			"Simulation",
			"A custom Gaggia Classic Pro concept uses a synthetic PID temperature model, bounded heater output and its own traceable espresso cup. No real controller is connected.",
			["brewing"],
			"machine-data",
		),
		(
			"Material genealogy",
			"Sample",
			"The scenario trace follows material parents; orders remain separate business inputs.",
			list(STAGE_IDS),
			"machine-data",
		),
		(
			"Machine records and OEE",
			"Sample",
			"Named Machine definitions, sample observations and packaging OEE share the existing replay.",
			["processing", "drying", "green", "roasting", "packaging", "brewing"],
			"machine-data",
		),
		(
			"Work instructions",
			"Sample",
			"Draft schema-aligned templates and pure-rule capture evaluations; no executed runs or approvals.",
			list(STAGE_IDS),
			"work-instructions",
		),
		(
			"Arabica NPI and requirements",
			"Proposed",
			"Six undecided gates, coffee-specific deliverables and an unverified requirements trace.",
			list(STAGE_IDS),
			"life-sciences",
		),
		(
			"Tech transfer and validation",
			"Proposed",
			"Draft transfer mapping and an optional qualification example; no approved limits or qualification result.",
			["processing", "drying", "roasting", "packaging", "brewing"],
			"life-sciences",
		),
		(
			"Facility utilities",
			"Sample",
			"Plot, bench, trellis and irrigation asset definitions; no live Building Point readings or weather API.",
			["land", "nursery", "trellis", "cultivation"],
			"building-management",
		),
		(
			"Commissioning and loop checks",
			"Guide only",
			"Local readiness evidence and instrument checks are not simulated or certified.",
			["processing", "drying", "roasting", "packaging"],
			"commissioning",
		),
		(
			"P&ID and signal mapping",
			"Guide only",
			"No P&ID, DEXPI import or actual instrument register is supplied.",
			["processing", "drying", "roasting"],
			"pid",
		),
		(
			"Maintenance, PFMEA and risk",
			"Guide only",
			"No maintenance execution, PFMEA scoring or safety-risk acceptance is claimed.",
			["harvest", "processing", "drying", "roasting", "packaging"],
			"risk-management",
		),
		(
			"Production scheduling",
			"Guide only",
			"The replay has a fixed teaching sequence, not a finite-capacity Production Schedule or ERP demand plan.",
			["processing", "drying", "green", "roasting", "packaging"],
			"scheduling",
		),
		(
			"Statistical process control",
			"Guide only",
			"Sparse replay measurements do not establish control limits or process capability. No SPC conclusion is claimed.",
			["drying", "roasting", "packaging", "brewing"],
			"spc",
		),
		(
			"Process mining",
			"Sample",
			"The replay uses FoaMES event-log discovery and OCEL export; it does not infer a real farm's process performance.",
			list(STAGE_IDS),
			"process-mining",
		),
		(
			"ERP and physical control",
			"Not connected",
			"No ERP stock movements, external writes or equipment commands occur.",
			["harvest", "packaging", "delivery"],
			"adapters",
		),
	)
	return [
		{
			"feature": feature,
			"status": status,
			"summary": summary,
			"stage_ids": stages,
			"asset_ids": ["DEMO-ASSET-ESPRESSO"]
			if feature == "Espresso PID replay"
			else [a["id"] for a in assets if set(stages) & set(a["stage_ids"])],
			"work_instruction_ids": [f"DEMO-WI-{stage.upper()}" for stage in stages] + ["DEMO-WI-ESPRESSO"]
			if feature == "Work instructions"
			else ["DEMO-WI-ESPRESSO"]
			if feature == "Espresso PID replay"
			else [],
			"guide_path": f"docs/{guide}.md",
		}
		for feature, status, summary, stages, guide in rows
	]


def build_explorer(scenarios) -> dict:
	"""Build independent static view records from the already-built scenario list."""
	assets = _assets(scenarios)
	return deepcopy(
		{
			"schema_version": 1,
			"simulation": True,
			"note": SAMPLE_NOTE,
			"assets": assets,
			"work_instructions": _work_instructions(assets, scenarios),
			"npi": _npi(assets),
			"coverage": _coverage(assets),
			"stage_views": STAGE_VIEWS,
		}
	)
