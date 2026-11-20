# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0
"""Build a portable, fictional coffee replay using FoaMES's actual pure modules.

Run from the repository root: python examples/coffee/build.py --out <directory>.
The output is static and never reads a site, writes production records or controls equipment.
Every quantity and acceptance limit is a teaching assumption, not a farm or recipe claim.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from espresso import make_espresso_scenario
from explorer import build_explorer

from foames.foames_mes.counters import counter_delta
from foames.foames_mes.oee import compute_oee, ledger_from_states
from foames.foames_process_mining.discovery import discover_dfg
from foames.foames_process_mining.eventlog import Event, EventLog
from foames.foames_process_mining.ocel import to_ocel

HERE = Path(__file__).resolve().parent
SCENARIO_IDS = ("normal", "moisture_hold", "network_gap", "recall", "espresso_pid")
STAGES = (
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
TIMES = (
	"2023-03-01T10:00:00-10:00",
	"2023-05-01T10:00:00-10:00",
	"2024-04-15T10:00:00-10:00",
	"2026-10-15T10:00:00-10:00",
	"2026-11-02T08:00:00-10:00",
	"2026-11-02T12:00:00-10:00",
	"2026-11-12T10:00:00-10:00",
	"2026-11-13T10:00:00-10:00",
	"2026-11-16T08:20:00-10:00",
	"2026-11-16T10:30:00-10:00",
	"2026-11-18T09:02:00-10:00",
	"2026-11-18T09:05:00-10:00",
)
ACTIVITIES = (
	"Approve planting plot",
	"Release nursery cohort",
	"Inspect trained rows",
	"Record field scouting",
	"Receive ripe cherry",
	"Complete wet processing",
	"Release dry parchment",
	"Release green lot",
	"Cool and sample roast",
	"Release packages and receive at cafe",
	"Complete filter brew",
	"Confirm cup handoff",
)
RECORD_IDS = (
	"DEMO-PLOT-01",
	"DEMO-NURSERY-01",
	"DEMO-ROW-01",
	"DEMO-SCOUT-01",
	"DEMO-CHERRY-01",
	"DEMO-WET-01",
	"DEMO-DRY-01",
	"DEMO-GREEN-01",
	"DEMO-ROAST-01",
	"DEMO-PACK-01",
	"DEMO-BREW-01",
	"DEMO-CUP-01",
)


def metric(label, value, unit=""):
	return {"label": label, "value": value, "unit": unit}


def node(identity, stage, label, parents, quantity=None, unit="", status="Released"):
	return {
		"id": identity,
		"stage": stage,
		"label": label,
		"parent_ids": parents,
		"quantity": quantity,
		"unit": unit,
		"status": status,
	}


def descendants(nodes, identity):
	"""Bounded genealogy traversal; cycles and missing parents are rejected separately."""
	affected = {identity}
	for _ in nodes:
		more = {n["id"] for n in nodes if set(n["parent_ids"]) & affected}
		if more <= affected:
			break
		affected |= more
	return sorted(affected)


def validate_trace(nodes):
	by_id = {n["id"]: n for n in nodes}
	if len(by_id) != len(nodes):
		raise ValueError("Duplicate genealogy id")
	visited, visiting = set(), set()

	def visit(identity):
		if identity not in by_id:
			raise ValueError(f"Unknown parent: {identity}")
		if identity in visiting:
			raise ValueError("Cyclic genealogy")
		if identity in visited:
			return
		visiting.add(identity)
		for parent in by_id[identity]["parent_ids"]:
			visit(parent)
		visiting.remove(identity)
		visited.add(identity)

	for identity in by_id:
		visit(identity)


def _packaging_oee(hold, gap, good, scrap):
	"""Compute the packaging window from state intervals and running counters."""
	intervals = (
		[]
		if hold
		else [
			(60 if gap else 70, "Running", False),
			(5, "Down", True),
			(10, "Down", False),
			(5, "Idle", False),
		]
	)
	# The uncovered ten minutes in the gap scenario remain Unknown in FoaMES.
	ledger = ledger_from_states(intervals, 0 if hold else 90)
	# Use running counter readings, including a baseline that produces zero delta.
	readings = {
		"good": [10000, 10000 + good],
		"scrap": [100, 100 + scrap],
	}
	totals = {key: counter_delta(None, vals[0]) + counter_delta(*vals) for key, vals in readings.items()}
	oee = asdict(compute_oee(ledger, totals["good"], totals["scrap"], 6))
	oee["coverage"] = ledger.coverage
	return readings, oee


def _scenario_metrics(hold, gap, good, scrap):
	"""Explicit teaching measurements, in the same order as the journey stages."""
	return [
		[metric("Plot", "DEMO-PLOT-01"), metric("Soil review", "Approved"), metric("Area", 1, "ha")],
		[
			metric("Seeds sown", 1200, "seeds"),
			metric("Released seedlings", 1000, "plants"),
			metric("Nursery rejects", 200, "plants"),
		],
		[
			metric("Cultivation", "Kona Joe-inspired trellis"),
			metric("Inspection", "Complete"),
			metric("Assumed yield uplift", 0, "%"),
		],
		[
			metric("Field scouting", "Recorded"),
			metric("Row identity", "DEMO-ROW-01"),
			metric("Human review", "Complete"),
		],
		[metric("Cherry received", 1000, "kg"), metric("Harvest lot", "DEMO-CHERRY-01")],
		[metric("Wet parchment", 420, "kg"), metric("Separated pulp / liquid", 580, "kg")],
		[
			metric("Dry parchment", 210, "kg"),
			metric("Moisture sample", 13.5 if hold else 11, "%"),
			metric("Demo release band", "10-12", "%"),
		],
		[metric("Green coffee", 170, "kg"), metric("Parchment / grading rejects", 40, "kg")],
		[
			metric("Charge", 165, "kg"),
			metric("Roasted output", 138.6, "kg"),
			metric("Roast loss", 26.4, "kg"),
		],
		[
			metric("Released packages", good, "x 250 g"),
			metric("Rejected packages", scrap, "bags"),
			metric("Retained sample", 0.1, "kg"),
			metric("Unfilled inventory", 25 if gap else 0, "kg"),
		],
		[
			metric("Dose", 18, "g"),
			metric("Beverage", 300, "g"),
			metric("TDS", 1.2, "%"),
			metric("Extraction", 20, "%"),
		],
		[metric("Order", "DEMO-ORDER-01"), metric("Handoff", "Recorded at 09:05 HST")],
	]


def _stage_notes():
	"""Explain the assumptions behind each stage without implying real operations."""
	return [
		"A fictional plot and soil review establish provenance. No location or soil measurement describes a real farm.",
		"Seed lot DEMO-SEED-01 becomes a nursery cohort. Plant counts are not coffee mass.",
		"The producer-described method is attributed; the independent paper is pending. No yield benefit is assumed.",
		"Elapsed crop growth is years, not the few seconds used to explore this replay.",
		"One illustrative harvest of 1,000 kg is traced from a known row. It is not a per-hectare yield prediction.",
		"Masses are teaching assumptions. The simplified cherry balance excludes added wash water; utility water needs a separate meter.",
		"11% passes this fictional site's 10-12% moisture band. This band is not a universal specification or current grading law.",
		"Dry milling removes 40 kg of parchment and grading rejects; the approved green lot is stored with its identity.",
		"5 kg is removed before a 165 kg roast charge. Cooling and sensory approval precede package release. No operating roast recipe is prescribed.",
		"The 90-minute packaging window includes a recorded 10-minute stop. A simulated shipment and cafe receipt preserve package identity.",
		"A 250 g bag supplies an 18 g dose, leaving 232 g. 18 g coffee + 336 g water becomes 300 g beverage and 54 g wet grounds / retained water / evaporation.",
		"Only an explicit simulated handoff event marks the cup delivered. Delivery is not inferred from brewing or elapsed time.",
	]


def _stage_records(hold, metrics, notes):
	"""Create stage observations and leave held downstream work unexecuted."""
	stages = {}
	for i, stage in enumerate(STAGES):
		record = {
			"status": "complete",
			"record_id": RECORD_IDS[i],
			"time": TIMES[i],
			"metrics": metrics[i],
			"note": notes[i],
		}
		if hold:
			if i == 6:
				record["status"] = "held"
			elif i > 6:
				record.update(
					status="pending",
					record_id=None,
					time=None,
					metrics=[],
					note="Not executed: the upstream dry parchment is held.",
				)
		stages[stage] = record
	return stages


def _scenario_trace(hold, good):
	"""Build only genealogy records supported by the selected scenario."""
	trace = [
		node("DEMO-PLOT-01", "land", "Approved land plot", [], 1, "ha"),
		node("DEMO-SEED-01", "nursery", "Seed lot", [], 1200, "seeds"),
		node("DEMO-NURSERY-01", "nursery", "Nursery cohort", ["DEMO-SEED-01"], 1000, "plants"),
		node(
			"DEMO-ROW-01",
			"trellis",
			"Trellised planted row",
			["DEMO-PLOT-01", "DEMO-NURSERY-01"],
			1000,
			"plants",
		),
		node("DEMO-SCOUT-01", "cultivation", "Field scouting record", ["DEMO-ROW-01"]),
		node("DEMO-CHERRY-01", "harvest", "Cherry harvest lot", ["DEMO-ROW-01", "DEMO-SCOUT-01"], 1000, "kg"),
		node("DEMO-WET-01", "processing", "Wet parchment lot", ["DEMO-CHERRY-01"], 420, "kg"),
		node(
			"DEMO-DRY-01",
			"drying",
			"Dry parchment lot",
			["DEMO-WET-01"],
			210,
			"kg",
			"Held" if hold else "Released",
		),
	]
	if not hold:
		trace += [
			node("DEMO-GREEN-01", "green", "Green coffee lot", ["DEMO-DRY-01"], 170, "kg"),
			node("DEMO-ROAST-01", "roasting", "Cooled roast batch", ["DEMO-GREEN-01"], 138.6, "kg"),
			node("DEMO-PACK-01", "packaging", "Packaged coffee lot", ["DEMO-ROAST-01"], good, "250 g bags"),
			node("DEMO-SHIP-01", "packaging", "Cafe receipt", ["DEMO-PACK-01"], 1, "250 g bag"),
			node("DEMO-ORDER-01", "brewing", "Cafe order", [], 1, "cup", "Fulfilled"),
			node(
				"DEMO-BREW-01", "brewing", "Filter brew", ["DEMO-SHIP-01", "DEMO-ORDER-01"], 300, "g beverage"
			),
			node(
				"DEMO-CUP-01",
				"delivery",
				"Delivered cup",
				["DEMO-BREW-01", "DEMO-ORDER-01"],
				1,
				"cup",
				"Delivered",
			),
		]
	return trace


def _scenario_suggestions(hold, gap, recall, stages):
	"""Attach review evidence while preserving observed history."""
	suggestions = []
	if hold:
		stages["drying"]["note"] = (
			"13.5% fails the fictional 10-12% moisture band. An operator must investigate, obtain a fresh sample and authorize release. This replay leaves the lot held."
		)
		suggestions.append(
			{
				"title": "Investigate drying hold",
				"evidence": "Sample DEMO-MOISTURE-02 = 13.5%; demo upper limit = 12%.",
				"action": "Review drying conditions and instrument calibration; sample again before a human release.",
			}
		)
	if gap:
		stages["packaging"]["status"] = "attention"
		stages["packaging"]["note"] = (
			"Ten minutes have no known state and remain Unknown loss. Observed running counters confirm 450 good packages, with no inferred production. The cup has its own observed brew and handoff records."
		)
		suggestions.append(
			{
				"title": "Investigate missing packaging signal",
				"evidence": "10 of 90 scheduled minutes are Unknown; good counter increased from 10,000 to 10,450.",
				"action": "Review the gateway and network. A secure tunnel can improve reachability; it does not fill missing evidence.",
			}
		)
	if recall:
		for stage in ("packaging", "brewing", "delivery"):
			stages[stage]["status"] = "attention"
		stages["packaging"]["note"] = (
			"A later retained-sample review raises a package-integrity concern. Trace the package lot forward; a person decides and records any hold, recall or customer notification."
		)
		suggestions.append(
			{
				"title": "Review package-lot containment",
				"evidence": "Simulated retained-sample concern on DEMO-PACK-01 after the recorded cup handoff.",
				"action": "Review inventory, cafe receipt and delivered cup. This demo does not notify customers or reverse history.",
			}
		)
	return suggestions


def _mass_balances(hold, gap, good, scrap):
	"""Keep each material transformation and its named nonproduct streams explicit."""
	balances = [
		{
			"stage": "processing",
			"input_kg": 1000,
			"output_kg": 420,
			"other_kg": 580,
			"other_label": "Separated pulp / liquid (added wash water excluded)",
		},
		{
			"stage": "drying",
			"input_kg": 420,
			"output_kg": 210,
			"other_kg": 210,
			"other_label": "Evaporated moisture",
		},
	]
	if not hold:
		balances += [
			{
				"stage": "green",
				"input_kg": 210,
				"output_kg": 170,
				"other_kg": 40,
				"other_label": "Parchment and grading rejects",
			},
			{
				"stage": "roasting",
				"input_kg": 170,
				"output_kg": 138.6,
				"other_kg": 31.4,
				"other_label": "5 kg sorting rejects + 26.4 kg roast loss",
			},
			{
				"stage": "packaging",
				"input_kg": 138.6,
				"output_kg": good * 0.25,
				"other_kg": 26.1 if gap else 1.1,
				"other_streams_kg": {
					"rejected_packages": scrap * 0.25,
					"retained_sample": 0.1,
					"unfilled_inventory": 25 if gap else 0,
				},
				"other_label": f"1 kg rejected packs + 0.1 kg retained sample + {25 if gap else 0} kg unfilled inventory",
			},
			{
				"stage": "brewing",
				"input_kg": 0.354,
				"output_kg": 0.300,
				"other_kg": 0.054,
				"other_label": "Wet grounds, retained water and evaporation; includes 336 g added water",
			},
		]
	return balances


def _scenario_events(hold, recall, stages):
	"""Record completed activities, including the hold or later package concern."""
	events = [
		{
			"stage": stage,
			"activity": ACTIVITIES[i],
			"timestamp": TIMES[i],
			"record_id": stages[stage]["record_id"],
			"related_record_ids": ["DEMO-SHIP-01"] if stage == "packaging" else [],
		}
		for i, stage in enumerate(STAGES)
		if not hold or i < 6
	]
	if hold:
		events.append(
			{
				"stage": "drying",
				"activity": "Hold parchment after moisture sample",
				"timestamp": TIMES[6],
				"record_id": "DEMO-DRY-01",
			}
		)
	if recall:
		events.append(
			{
				"stage": "packaging",
				"activity": "Flag retained-sample concern",
				"timestamp": "2026-11-18T12:00:00-10:00",
				"record_id": "DEMO-PACK-01",
			}
		)
	return events


def _scenario_cup(hold, recall):
	"""Keep a held journey distinct from a recorded cup and its later review."""
	if hold:
		return {
			"id": None,
			"status": "Not reached",
			"beverage_g": 0,
			"coffee_dose_g": 0,
			"tds_percent": None,
			"extraction_percent": None,
			"handoff_at": None,
		}
	return {
		"id": "DEMO-CUP-01",
		"status": "Recall review" if recall else "Delivered",
		"beverage_g": 300,
		"coffee_dose_g": 18,
		"tds_percent": 1.2,
		"extraction_percent": 300 * (1.2 / 100) / 18 * 100,
		"handoff_at": TIMES[-1],
	}


def make_scenario(kind="normal"):
	if kind == "espresso_pid":
		result = make_espresso_scenario(make_scenario("normal"))
		result["process_graph"] = discover_dfg(event_log(result)).to_dict()
		validate_trace(result["trace"])
		return result
	good_counts = {"normal": 550, "moisture_hold": 0, "network_gap": 450, "recall": 550}
	if kind not in good_counts:
		raise ValueError("Unknown scenario")
	hold = kind == "moisture_hold"
	gap = kind == "network_gap"
	recall = kind == "recall"
	good = good_counts[kind]
	scrap = 0 if hold else 4
	readings, oee = _packaging_oee(hold, gap, good, scrap)
	metrics = _scenario_metrics(hold, gap, good, scrap)
	stages = _stage_records(hold, metrics, _stage_notes())
	trace = _scenario_trace(hold, good)
	suggestions = _scenario_suggestions(hold, gap, recall, stages)
	balances = _mass_balances(hold, gap, good, scrap)
	events = _scenario_events(hold, recall, stages)
	titles = {
		"normal": "Seed to delivered cup",
		"moisture_hold": "Moisture hold",
		"network_gap": "Missing machine signal",
		"recall": "Trace a package concern",
	}
	summaries = {
		"normal": "Follow a fictional lot across three years, from a planting decision to a recorded cafe handoff.",
		"moisture_hold": "A failed moisture sample stops the journey before dry milling. Downstream output remains unproduced.",
		"network_gap": "Missing state data stays Unknown loss. Only observed counter differences count as production.",
		"recall": "A concern found after delivery shows which downstream records need a person's review; history remains intact.",
	}
	result = {
		"id": kind,
		"title": titles[kind],
		"summary": summaries[kind],
		"stages": stages,
		"trace": trace,
		"oee": oee,
		"counter_readings": readings,
		"events": events,
		"mass_balance": balances,
		"suggestions": suggestions,
		"recall_affected_ids": descendants(trace, "DEMO-PACK-01") if recall else [],
		"cup": _scenario_cup(hold, recall),
	}
	result["process_graph"] = discover_dfg(event_log(result)).to_dict()
	validate_trace(trace)
	return result


def event_log(scenario):
	by_id = {node["id"]: node for node in scenario["trace"]}
	return EventLog(
		[
			Event(
				"DEMO-JOURNEY-01",
				e["activity"],
				datetime.fromisoformat(e["timestamp"]),
				resource="Simulated operator",
				attributes={"simulation": True, "stage": e["stage"]},
				objects={
					"record": [
						e["record_id"],
						*by_id[e["record_id"]]["parent_ids"],
						*e.get("related_record_ids", []),
					]
				},
			)
			for e in scenario["events"]
		],
		name=f"FoaMES coffee / {scenario['id']}",
	)


def coffee_ocel(scenario):
	"""Keep material and order provenance as OCEL 2.0 object relationships."""
	exported = to_ocel(event_log(scenario))
	parents = {node["id"]: node["parent_ids"] for node in scenario["trace"]}
	for obj in exported["objects"]:
		if obj["type"] == "record":
			obj["relationships"] = [
				{
					"objectId": identity,
					"qualifier": "fulfillsOrder" if identity == "DEMO-ORDER-01" else "derivedFrom",
				}
				for identity in parents[obj["id"]]
			]
	return exported


def _source_revision():
	"""Read revision metadata when Git is available, including source archives."""
	git_executable = shutil.which("git")
	if git_executable is None:
		return "source archive"
	git_executable = str(Path(git_executable).resolve())
	try:
		toplevel = subprocess.check_output(
			[git_executable, "rev-parse", "--show-toplevel"], cwd=ROOT, text=True
		).strip()
		if Path(toplevel).resolve() != ROOT:
			return "source archive"
		return subprocess.check_output([git_executable, "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
	except (subprocess.CalledProcessError, OSError):
		return "source archive"


def build_data():
	catalog = json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))
	if tuple(s["id"] for s in catalog["stages"]) != STAGES:
		raise ValueError("Catalog stage order disagrees with the replay")
	sources = {s["id"] for s in catalog["sources"]}
	for stage in catalog["stages"]:
		if not set(stage["source_ids"]) <= sources:
			raise ValueError(f"Unknown source for {stage['id']}")
	revision = _source_revision()
	data = copy.deepcopy(catalog)
	data.update(
		{
			"scenarios": [make_scenario(k) for k in SCENARIO_IDS],
			"engine": {
				"name": "FoaMES computed replay",
				"revision": revision,
				"modules": [
					"foames.foames_mes.counters",
					"foames.foames_mes.oee",
					"foames.foames_process_mining.discovery",
					"foames.foames_process_mining.ocel",
					"foames.foames_mes.work_instructions",
					"foames.foames_life_sciences.npi",
					"foames.foames_life_sciences.requirements",
				],
			},
		}
	)
	data["explorer"] = build_explorer(data["scenarios"])
	return data


def build(destination):
	destination = Path(destination).resolve()
	# Never overwrite the hand-authored web source or repository checkout.
	if destination in {ROOT, HERE, HERE / "web"}:
		raise ValueError("Choose a separate output directory")
	data = build_data()
	output_names = ["index.html", "app.js", "styles.css", "data.json"]
	output_names.extend(f"{scenario['id']}.ocel.json" for scenario in data["scenarios"])
	# Check every artifact before writing any: even a late export may redirect outside the build.
	for name in output_names:
		if (destination / name).is_symlink():
			raise ValueError(f"Build output must not be a symlink: {name}")
	destination.mkdir(parents=True, exist_ok=True)
	for name in ("index.html", "app.js", "styles.css"):
		shutil.copyfile(HERE / "web" / name, destination / name)
	(destination / "data.json").write_text(
		json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
	)
	for scenario in data["scenarios"]:
		(destination / f"{scenario['id']}.ocel.json").write_text(
			json.dumps(coffee_ocel(scenario), indent=2) + "\n",
			encoding="utf-8",
		)
	return data


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--out", type=Path, required=True)
	args = parser.parse_args()
	build(args.out)
	print(f"Built coffee demo: {args.out.resolve()}")
