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

"""Risk scores, ratings, tolerance, the hierarchy of controls and the findings. No Frappe site needed."""

import unittest
from datetime import date

from foames.foames_risk.risk import (
	CONTROL_LEVELS,
	DEFAULT_BANDS,
	assess,
	control_schedule,
	findings,
	heat_map,
	indicator_breached,
	next_due,
	normalise_bands,
	rating,
	review_interval,
	score,
	strongest_control,
	within_tolerance,
)
from foames.foames_risk.templates import CATEGORIES, TEMPLATES

TODAY = date(2026, 11, 15)


def control(level, status="In Place", **extra):
	return {"control": f"{level} control", "control_level": level, "status": status, **extra}


def risk(**overrides):
	values = {
		"inherent_impact": 5,
		"inherent_likelihood": 4,
		"residual_impact": 4,
		"residual_likelihood": 2,
		"response": "Reduce",
		"controls": [control("Engineering Controls")],
		"tolerance": "Moderate",
		"risk_statement": "If solvent vapour builds up, then workers may be overcome.",
	}
	values.update(overrides)
	return values


class TestScoresAndRatings(unittest.TestCase):
	def test_score_is_impact_times_likelihood(self):
		self.assertEqual(score(5, 5), 25)
		self.assertEqual(score(1, 1), 1)
		self.assertEqual(score(3, 4), 12)

	def test_ratings_outside_one_to_five_are_refused(self):
		for bad in (0, 6, None, "x", 2.5):
			with self.assertRaises(ValueError):
				score(bad, 3)

	def test_default_bands(self):
		self.assertEqual([rating(s) for s in (1, 3)], ["Very Low", "Very Low"])
		self.assertEqual([rating(s) for s in (4, 6)], ["Low", "Low"])
		self.assertEqual([rating(s) for s in (8, 12)], ["Moderate", "Moderate"])
		self.assertEqual([rating(s) for s in (15, 16)], ["High", "High"])
		self.assertEqual([rating(s) for s in (20, 25)], ["Very High", "Very High"])

	def test_bands_can_be_set_and_must_rise(self):
		self.assertEqual(rating(10, {"Moderate": 9}), "High")
		self.assertEqual(normalise_bands({"Low": None}), DEFAULT_BANDS)
		with self.assertRaises(ValueError):
			normalise_bands({"Low": 2, "Very Low": 3})
		with self.assertRaises(ValueError):
			normalise_bands({"High": 25})

	def test_tolerance(self):
		self.assertTrue(within_tolerance("Moderate", "Moderate"))
		self.assertTrue(within_tolerance("Low", "Moderate"))
		self.assertFalse(within_tolerance("High", "Moderate"))
		self.assertTrue(within_tolerance("Moderate", None))


class TestAssess(unittest.TestCase):
	def test_derived_values(self):
		result = assess(risk())
		self.assertEqual(result["errors"], [])
		self.assertEqual(result["inherent_score"], 20)
		self.assertEqual(result["inherent_rating"], "Very High")
		self.assertEqual(result["residual_score"], 8)
		self.assertEqual(result["residual_rating"], "Moderate")
		self.assertTrue(result["within_tolerance"])
		self.assertEqual(result["strongest_control"], "Engineering Controls")
		self.assertEqual(result["controls_in_place"], 1)

	def test_no_residual_means_no_reduction(self):
		result = assess(risk(residual_impact=None, residual_likelihood=None, response="Accept", controls=[]))
		self.assertEqual(result["errors"], [])
		self.assertEqual(result["residual_score"], 20)
		self.assertFalse(result["within_tolerance"])

	def test_residual_never_above_inherent(self):
		result = assess(risk(residual_impact=5, residual_likelihood=5))
		self.assertIn("cannot be higher", " ".join(result["errors"]))

	def test_accept_keeps_the_inherent_rating(self):
		result = assess(risk(response="Accept"))
		self.assertIn("Accept response takes no action", " ".join(result["errors"]))

	def test_reduction_needs_a_working_control(self):
		self.assertIn("control in place", " ".join(assess(risk(controls=[]))["errors"]))
		planned = [control("Engineering Controls", status="Planned")]
		self.assertIn("control in place", " ".join(assess(risk(controls=planned))["errors"]))
		failed = [control("Engineering Controls", verification_result="Fail")]
		self.assertIn("control in place", " ".join(assess(risk(controls=failed))["errors"]))

	def test_transfer_and_share_name_the_other_party(self):
		for response in ("Transfer", "Share"):
			result = assess(risk(response=response, controls=[]))
			self.assertIn("organization the risk goes to", " ".join(result["errors"]))
			result = assess(risk(response=response, controls=[], transfer_to="Insurer"))
			self.assertEqual(result["errors"], [])

	def test_target_not_above_residual(self):
		result = assess(risk(target_impact=4, target_likelihood=3))
		self.assertIn("target impact", " ".join(result["errors"]))
		result = assess(risk(target_impact=3, target_likelihood=1))
		self.assertEqual(result["target_score"], 3)
		self.assertEqual(result["target_rating"], "Very Low")

	def test_statement_form_is_a_warning(self):
		self.assertEqual(assess(risk())["warnings"], [])
		result = assess(risk(risk_statement="The ventilation fan is broken."))
		self.assertEqual(result["errors"], [])
		self.assertEqual(len(result["warnings"]), 1)

	def test_missing_inherent_rating_stops_early(self):
		result = assess(risk(inherent_impact=None))
		self.assertEqual(len(result["errors"]), 1)
		self.assertNotIn("residual_score", result)

	def test_unknown_control_level(self):
		result = assess(risk(controls=[control("Engineering Controls"), control("Prayer")]))
		self.assertIn("Unknown control level Prayer", result["errors"])


class TestHierarchy(unittest.TestCase):
	def test_strongest_control(self):
		controls = [control("PPE"), control("Work Practices"), control("Substitution", status="Planned")]
		self.assertEqual(strongest_control(controls), "Work Practices")
		controls.append(control("Elimination", effectiveness="Ineffective"))
		self.assertEqual(strongest_control(controls), "Work Practices")
		controls.append(control("Engineering Controls"))
		self.assertEqual(strongest_control(controls), "Engineering Controls")
		self.assertIsNone(strongest_control([]))

	def test_every_level_is_ranked(self):
		for level in CONTROL_LEVELS:
			self.assertEqual(strongest_control([control(level)]), level)


class TestSchedules(unittest.TestCase):
	def test_next_due(self):
		self.assertEqual(next_due(date(2026, 1, 1), date(2025, 1, 1), 30), date(2026, 1, 31))
		self.assertEqual(next_due(None, date(2026, 1, 1), 10), date(2026, 1, 11))
		self.assertIsNone(next_due(None, None, 10))
		self.assertIsNone(next_due(date(2026, 1, 1), None, 0))

	def test_review_interval_by_rating(self):
		self.assertEqual(review_interval("Moderate", None), 365)
		self.assertEqual(review_interval("High", None), 90)
		self.assertEqual(review_interval("Very High", None, {"high_risk_review_days": 30}), 30)
		self.assertEqual(review_interval("Very High", 14), 14)

	def test_control_schedule(self):
		c = control("Engineering Controls", implemented_on=date(2026, 1, 1), verification_interval_days=90)
		self.assertEqual(control_schedule(c, TODAY)["next_verification_on"], date(2026, 4, 1))
		self.assertTrue(control_schedule(c, TODAY)["overdue"])
		c["verified_on"] = date(2026, 11, 1)
		self.assertFalse(control_schedule(c, TODAY)["overdue"])
		planned = control("PPE", status="Planned", implemented_on=date(2026, 1, 1))
		self.assertIsNone(control_schedule(planned, TODAY)["next_verification_on"])

	def test_indicator(self):
		self.assertTrue(indicator_breached(5, 3))
		self.assertFalse(indicator_breached(3, 3))
		self.assertTrue(indicator_breached(1, 3, "Below"))
		self.assertFalse(indicator_breached(None, 3))

	def test_heat_map(self):
		grid = heat_map(
			[
				{"residual_impact": 5, "residual_likelihood": 1},
				{"residual_impact": 5, "residual_likelihood": 1},
				{"residual_impact": 1, "residual_likelihood": 5},
				{"residual_impact": None, "residual_likelihood": 3},
			]
		)
		self.assertEqual(grid[0][0], 2)
		self.assertEqual(grid[4][4], 1)
		self.assertEqual(sum(sum(row) for row in grid), 3)


def open_risk(**overrides):
	values = {
		"name": "RISK-2026-00001",
		"title": "Solvent vapour",
		"residual_rating": "Moderate",
		"residual_score": 8,
		"tolerance": "Moderate",
		"within_tolerance": True,
		"accepted": False,
		"next_review_on": date(2027, 1, 1),
		"apply_hierarchy": True,
		"controls": [],
		"indicators": [],
	}
	values.update(overrides)
	return values


def kinds(found):
	return sorted(f["rule_key"].split(":")[1] for f in found)


class TestFindings(unittest.TestCase):
	def test_quiet_risk_raises_nothing(self):
		self.assertEqual(findings(open_risk(), TODAY), [])

	def test_above_tolerance_until_accepted(self):
		r = open_risk(residual_rating="Very High", within_tolerance=False)
		found = findings(r, TODAY)
		self.assertIn("tolerance", kinds(found))
		self.assertEqual(next(f for f in found if "tolerance" in f["rule_key"])["severity"], "Critical")
		r["accepted"] = True
		self.assertNotIn("tolerance", kinds(findings(r, TODAY)))

	def test_review_overdue(self):
		found = findings(open_risk(next_review_on=date(2026, 11, 1)), TODAY)
		self.assertEqual(kinds(found), ["review"])
		self.assertEqual(found[0]["severity"], "Info")

	def test_high_hazard_on_lower_order_controls(self):
		r = open_risk(
			residual_rating="High",
			within_tolerance=True,
			controls=[control("PPE"), control("Work Practices")],
		)
		self.assertEqual(kinds(findings(r, TODAY)), ["hierarchy"])
		r["controls"].append(control("Engineering Controls"))
		self.assertEqual(kinds(findings(r, TODAY)), [])
		r = open_risk(residual_rating="High", apply_hierarchy=False, controls=[control("PPE")])
		self.assertEqual(kinds(findings(r, TODAY)), [])

	def test_control_verification_and_failure(self):
		c = control("Engineering Controls", name="row1", next_verification_on=date(2026, 10, 1))
		self.assertEqual(kinds(findings(open_risk(controls=[c]), TODAY)), ["verify"])
		c.update(next_verification_on=None, verification_result="Fail")
		found = findings(open_risk(controls=[c]), TODAY)
		self.assertEqual(kinds(found), ["ineffective"])
		self.assertTrue(found[0]["rule_key"].endswith(":row1"))

	def test_evidence_indicator_target_and_source(self):
		r = open_risk(
			evidence_issues=[
				{"control": "LEV", "doctype": "Maintenance Plan", "name": "MPL-1", "problem": "is overdue"}
			],
			indicators=[
				{
					"name": "i1",
					"indicator": "Near misses",
					"breached": True,
					"current_value": 4,
					"threshold": 2,
				}
			],
			target_date=date(2026, 11, 1),
			target_score=4,
			sources=[{"doctype": "Hazard Assessment", "name": "HAZ-1", "rating": "High"}],
		)
		self.assertEqual(kinds(findings(r, TODAY)), ["evidence", "indicator", "source", "target"])

	def test_titles_fit(self):
		r = open_risk(title="x" * 300, within_tolerance=False, next_review_on=date(2026, 1, 1))
		for f in findings(r, TODAY):
			self.assertLessEqual(len(f["title"]), 140)
			self.assertTrue(f["title"].startswith("Risk RISK-2026-00001: "))

	def test_findings_point_at_the_risk(self):
		f = findings(open_risk(next_review_on=date(2026, 1, 1)), TODAY)[0]
		self.assertEqual(f["reference_doctype"], "Enterprise Risk")
		self.assertEqual(f["reference_name"], "RISK-2026-00001")
		self.assertIn(f["category"], ("Other",))


class TestTemplates(unittest.TestCase):
	def test_templates_are_valid(self):
		names = {c[0] for c in CATEGORIES}
		titles = set()
		for tpl in TEMPLATES:
			self.assertIn(tpl["category"], names)
			self.assertNotIn(tpl["title"], titles)
			titles.add(tpl["title"])
			result = assess(
				{
					"inherent_impact": tpl["inherent_impact"],
					"inherent_likelihood": tpl["inherent_likelihood"],
					"risk_statement": tpl["risk_statement"],
					"controls": [
						{"control_level": level, "status": "Planned"} for _c, level, _f, _m in tpl["controls"]
					],
				}
			)
			self.assertEqual(result["errors"], [], tpl["title"])
			self.assertEqual(result["warnings"], [], tpl["title"])

	def test_hazard_templates_reach_above_ppe(self):
		hazards = {"Safety and Health", "Environmental"}
		for tpl in TEMPLATES:
			if tpl["category"] in hazards:
				levels = [level for _c, level, _f, _m in tpl["controls"]]
				self.assertIsNotNone(
					strongest_control([{"control_level": lvl, "status": "In Place"} for lvl in levels])
				)
				self.assertTrue(
					any(lvl in ("Elimination", "Substitution", "Engineering Controls") for lvl in levels),
					tpl["title"],
				)


if __name__ == "__main__":
	unittest.main()
