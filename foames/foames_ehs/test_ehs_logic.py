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

"""EHS arithmetic and rules: recordability, rates, risk, exposure, permits and findings. No Frappe site needed."""

import unittest
from datetime import date, datetime, timedelta

from foames.foames_ehs.ehs import (
	assess_hazard,
	capped_days,
	classify_incident,
	evaluate_exposure,
	expired_permit_findings,
	exposure_findings,
	exposure_status,
	hazard_review_findings,
	incidence_rate,
	incident_rates,
	investigation_findings,
	lockout_findings,
	locks_applied,
	next_review,
	noise_allowed_hours,
	noise_dose,
	noise_twa,
	osha_outcome,
	overdue_action_findings,
	permit_problems,
	risk_level,
	risk_score,
	serious_incident_findings,
	strongest_control,
	twa,
)

START = datetime(2026, 11, 2, 7, 0, 0)


def injury(**fields):
	return {"incident_type": "Injury or Illness", "work_related": 1, **fields}


def point(name="Main disconnect", **fields):
	return {"isolation_point": name, "lock_id": "L-17", "verified": 1, **fields}


def permit(**fields):
	values = {
		"name": "PTW-0001",
		"permit_type": "Lockout Tagout",
		"status": "Active",
		"machine": "PRESS-1",
		"valid_from": START,
		"valid_to": START + timedelta(hours=8),
		"issued_by": "supervisor@example.com",
		"performed_by": "fitter@example.com",
		"isolation_points": [point()],
	}
	values.update(fields)
	return values


class TestRecordability(unittest.TestCase):
	def test_most_serious_outcome_wins(self):
		self.assertEqual(osha_outcome(death=True, days_away=3), "Death")
		self.assertEqual(osha_outcome(days_away=2, days_restricted=5), "Days Away From Work")
		self.assertEqual(
			osha_outcome(days_restricted=1, medical_treatment=True), "Job Transfer or Restriction"
		)
		self.assertEqual(osha_outcome(medical_treatment=True), "Other Recordable Case")
		self.assertEqual(osha_outcome(loss_of_consciousness=True), "Other Recordable Case")
		self.assertEqual(osha_outcome(significant_diagnosis=True), "Other Recordable Case")
		self.assertIsNone(osha_outcome())

	def test_days_are_capped(self):
		self.assertEqual(capped_days(400), 180)
		self.assertEqual(capped_days(-3), 0)
		self.assertEqual(capped_days(None), 0)
		self.assertEqual(classify_incident(injury(days_away=250))["days_away"], 180)

	def test_only_work_related_injuries_are_recordable(self):
		self.assertTrue(classify_incident(injury(medical_treatment=1))["recordable"])
		self.assertFalse(classify_incident(injury(medical_treatment=1, work_related=0))["recordable"])
		# First aid stays first aid, whatever boxes are ticked: the record has to be reclassified.
		self.assertFalse(
			classify_incident({"incident_type": "First Aid", "medical_treatment": 1})["recordable"]
		)
		self.assertFalse(classify_incident({"incident_type": "Near Miss"})["recordable"])

	def test_dart_and_lost_time(self):
		away = classify_incident(injury(days_away=3))
		self.assertTrue(away["dart"] and away["lost_time"])
		restricted = classify_incident(injury(days_restricted=3))
		self.assertTrue(restricted["dart"])
		self.assertFalse(restricted["lost_time"])
		other = classify_incident(injury(medical_treatment=1))
		self.assertFalse(other["dart"] or other["lost_time"])
		death = classify_incident(injury(death=1))
		self.assertTrue(death["lost_time"])
		self.assertFalse(death["dart"])
		self.assertEqual(classify_incident(injury())["days_away"], 0)


class TestRates(unittest.TestCase):
	def test_incidence_rate(self):
		self.assertAlmostEqual(incidence_rate(3, 400_000), 1.5)
		self.assertIsNone(incidence_rate(3, 0))
		self.assertIsNone(incidence_rate(3, None))

	def test_rates_over_a_period(self):
		incidents = [
			injury(days_away=5),
			injury(days_restricted=2),
			injury(medical_treatment=1),
			{"incident_type": "First Aid"},
			{"incident_type": "Near Miss"},
			{"incident_type": "Near Miss"},
			{"incident_type": "Unsafe Condition"},
			{"incident_type": "Environmental Release"},
		]
		r = incident_rates(incidents, 200_000)
		self.assertEqual(r["incidents"], 8)
		self.assertEqual(r["recordable"], 3)
		self.assertEqual(r["dart"], 2)
		self.assertEqual(r["lost_time"], 1)
		self.assertEqual(r["days_away"], 5)
		self.assertEqual(r["days_restricted"], 2)
		self.assertEqual(r["leading"], 3)
		self.assertAlmostEqual(r["trir"], 3.0)
		self.assertAlmostEqual(r["dart_rate"], 2.0)
		self.assertAlmostEqual(r["ltir"], 1.0)
		self.assertAlmostEqual(r["severity_rate"], 5.0)
		self.assertAlmostEqual(r["near_miss_ratio"], 1.0)
		self.assertEqual(r["by_type"]["Near Miss"], 2)

	def test_no_hours_no_rates(self):
		r = incident_rates([{"incident_type": "Near Miss"}], None)
		self.assertIsNone(r["trir"])
		self.assertIsNone(r["near_miss_ratio"])


class TestRisk(unittest.TestCase):
	def test_matrix(self):
		self.assertEqual(risk_score(5, 5), 25)
		self.assertEqual(risk_score("3", 2.0), 6)
		for bad in (0, 6, 2.5, None, "x"):
			with self.assertRaises(ValueError):
				risk_score(bad, 3)
		self.assertEqual(
			[risk_level(s) for s in (1, 4, 5, 9, 10, 16, 20, 25)],
			["Low", "Low", "Medium", "Medium", "High", "High", "Very High", "Very High"],
		)

	def test_hierarchy(self):
		self.assertEqual(strongest_control(["PPE", "Engineering", "Administrative"]), "Engineering")
		self.assertIsNone(strongest_control([]))
		self.assertIsNone(strongest_control(["Hope"]))

	def test_assessment(self):
		a = assess_hazard(4, 5, 2, 5, ["Engineering", "PPE"])
		self.assertEqual((a["risk_score"], a["risk_level"]), (20, "Very High"))
		self.assertEqual((a["residual_score"], a["residual_level"]), (10, "High"))
		self.assertEqual(a["weaknesses"], [])
		weak = assess_hazard(4, 4, 3, 4, ["PPE", "Administrative"])
		self.assertEqual(weak["weaknesses"], ["relies on administrative controls only"])
		self.assertEqual(assess_hazard(5, 5)["weaknesses"], ["no controls recorded"])
		self.assertEqual(assess_hazard(5, 5)["residual_score"], 25)
		self.assertEqual(assess_hazard(2, 2, 1)["residual_score"], 2)
		with self.assertRaises(ValueError):
			assess_hazard(2, 2, 3, 3)

	def test_next_review(self):
		self.assertEqual(next_review(date(2026, 1, 1), 365), date(2027, 1, 1))
		self.assertEqual(next_review(datetime(2026, 1, 1, 9), 30), date(2026, 1, 31))
		self.assertIsNone(next_review(None, 365))
		self.assertIsNone(next_review(date(2026, 1, 1), 0))


class TestExposure(unittest.TestCase):
	def test_twa_counts_unsampled_time_as_zero(self):
		self.assertAlmostEqual(twa([(0.2, 240), (0.1, 240)]), 0.15)
		self.assertAlmostEqual(twa([(0.4, 240)]), 0.2)
		self.assertAlmostEqual(twa([(0.3, 600)]), 0.3)  # longer than the shift: average over what was sampled
		self.assertEqual(twa([]), 0.0)
		with self.assertRaises(ValueError):
			twa([(-1, 60)])

	def test_noise(self):
		self.assertAlmostEqual(noise_allowed_hours(90), 8.0)
		self.assertAlmostEqual(noise_allowed_hours(95), 4.0)
		self.assertAlmostEqual(noise_allowed_hours(85), 16.0)
		self.assertAlmostEqual(noise_dose([(90, 480)]), 100.0)
		self.assertAlmostEqual(noise_dose([(95, 240), (90, 240)]), 150.0)
		self.assertEqual(noise_dose([(79, 480)]), 0.0)
		self.assertAlmostEqual(noise_twa(100.0), 90.0)
		self.assertAlmostEqual(noise_twa(200.0), 95.0, places=2)
		self.assertAlmostEqual(noise_twa(50.0), 85.0, places=2)
		self.assertIsNone(noise_twa(0))

	def test_status(self):
		self.assertEqual(exposure_status(0.06, 0.05, 0.025), "Above Limit")
		self.assertEqual(exposure_status(0.05, 0.05, 0.025), "At or Above Action Level")
		self.assertEqual(exposure_status(0.01, 0.05, 0.025), "Below Action Level")
		self.assertEqual(exposure_status(0.01), "No Limit Set")
		self.assertEqual(exposure_status(None, 90, 85), "Below Action Level")

	def test_evaluate(self):
		noise = evaluate_exposure("Noise", [(92, 480)])
		self.assertEqual((noise["limit"], noise["action_level"]), (90.0, 85.0))
		self.assertAlmostEqual(noise["result"], 92.0, places=1)
		self.assertEqual(noise["status"], "Above Limit")
		quiet = evaluate_exposure("Noise", [(70, 480)])
		self.assertIsNone(quiet["result"])
		self.assertEqual(quiet["status"], "Below Action Level")
		silica = evaluate_exposure("Concentration", [(0.03, 480)], limit=0.05, action_level=0.025)
		self.assertEqual(silica["status"], "At or Above Action Level")
		self.assertAlmostEqual(silica["percent_of_limit"], 60.0)
		with self.assertRaises(ValueError):
			evaluate_exposure("Concentration", [(1, 60)], limit=1, action_level=2)
		with self.assertRaises(ValueError):
			evaluate_exposure("Guess", [])


class TestPermits(unittest.TestCase):
	def test_a_good_active_permit(self):
		self.assertEqual(permit_problems(permit()), [])

	def test_window(self):
		self.assertIn("the permit must end after it starts", permit_problems(permit(valid_to=START)))
		long = permit_problems(permit(valid_to=START + timedelta(hours=13)))
		self.assertTrue(any("at most 12 hours" in p for p in long))
		self.assertEqual(permit_problems(permit(valid_to=START + timedelta(hours=13)), max_hours=24), [])
		self.assertEqual(permit_problems(permit(valid_to=START + timedelta(hours=13)), max_hours=None), [])

	def test_people(self):
		self.assertIn(
			"the issuer cannot also be the person doing the work",
			permit_problems(permit(performed_by="supervisor@example.com")),
		)
		self.assertIn(
			"an active permit needs the person who issued it", permit_problems(permit(issued_by=None))
		)

	def test_isolation_before_work(self):
		self.assertIn(
			"a Lockout Tagout permit needs at least one isolation point",
			permit_problems(permit(isolation_points=[])),
		)
		self.assertEqual(permit_problems(permit(permit_type="Hot Work", isolation_points=[])), [])
		problems = permit_problems(permit(isolation_points=[point(lock_id=None, verified=0)]))
		self.assertIn("Main disconnect has no lock applied", problems)
		self.assertIn("Main disconnect is not verified at zero energy", problems)
		# Drafts may be incomplete.
		self.assertEqual(permit_problems(permit(status="Draft", isolation_points=[], issued_by=None)), [])

	def test_close_needs_locks_off(self):
		on = permit(status="Closed")
		self.assertIn("the lock on Main disconnect has not been removed", permit_problems(on))
		off = permit(status="Closed", isolation_points=[point(removed_on=START + timedelta(hours=7))])
		self.assertEqual(permit_problems(off), [])

	def test_locks_applied(self):
		p = permit(isolation_points=[point("A"), point("B", removed_on=START), point("C", lock_id=None)])
		self.assertEqual(locks_applied(p), ["A"])


class TestFindings(unittest.TestCase):
	def test_running_under_lockout(self):
		machines = [
			{"name": "PRESS-1", "status": "Running", "last_seen": START},
			{"name": "PRESS-2", "status": "Down", "last_seen": START},
		]
		permits = [
			permit(),
			permit(name="PTW-0002", machine="PRESS-2"),
			permit(name="PTW-0003", isolation_points=[point(removed_on=START)]),
		]
		found = lockout_findings(machines, permits)
		self.assertEqual(len(found), 1)
		f = found[0]
		self.assertEqual((f["category"], f["severity"]), ("Safety", "Critical"))
		self.assertEqual(f["reference_name"], "PTW-0001")
		self.assertEqual(f["evidence"]["locked_points"], ["Main disconnect"])

	def test_expired_permits(self):
		now = START + timedelta(hours=9)
		found = expired_permit_findings(
			[
				permit(),
				permit(name="PTW-0002", permit_type="Hot Work", isolation_points=[]),
				permit(name="PTW-0003", valid_to=START + timedelta(hours=10)),
				permit(name="PTW-0004", status="Closed"),
			],
			now,
		)
		self.assertEqual([f["reference_name"] for f in found], ["PTW-0001", "PTW-0002"])
		self.assertEqual([f["severity"] for f in found], ["Critical", "Warning"])

	def test_overdue_actions(self):
		today = date(2026, 11, 14)
		actions = [
			{
				"parent": "SINC-1",
				"name": "a1",
				"action": "Fit guard",
				"action_owner": "x@example.com",
				"due_on": date(2026, 11, 10),
			},
			{"parent": "SINC-1", "name": "a2", "action": "Retrain", "due_on": date(2026, 10, 1)},
			{"parent": "SINC-2", "name": "a3", "action": "Later", "due_on": today},
			{"parent": "SINC-2", "name": "a4", "action": "No date", "due_on": None},
		]
		found = overdue_action_findings(actions, today)
		self.assertEqual([f["severity"] for f in found], ["Warning", "Critical"])
		self.assertIn("has no owner", found[1]["suggestion"])

	def test_investigations(self):
		today = date(2026, 11, 14)
		found = investigation_findings(
			[
				{"name": "SINC-1", "incident_type": "Near Miss", "occurred_on": datetime(2026, 11, 1, 9)},
				{"name": "SINC-2", "occurred_on": datetime(2026, 11, 1, 9), "recordable": 1},
				{"name": "SINC-3", "occurred_on": datetime(2026, 11, 1, 9), "root_cause": "Guard missing"},
				{"name": "SINC-4", "occurred_on": datetime(2026, 11, 10, 9)},
				{"name": "SINC-5", "occurred_on": datetime(2026, 11, 1, 9), "status": "Closed"},
			],
			today,
		)
		self.assertEqual([f["reference_name"] for f in found], ["SINC-1", "SINC-2"])
		self.assertEqual([f["severity"] for f in found], ["Warning", "Critical"])

	def test_hazard_reviews(self):
		today = date(2026, 11, 14)
		found = hazard_review_findings(
			[
				{"name": "HAZ-1", "next_review_on": date(2026, 11, 1)},
				{
					"name": "HAZ-2",
					"next_review_on": date(2026, 12, 1),
					"weaknesses": ["relies on ppe controls only"],
					"residual_level": "High",
					"residual_score": 12,
				},
			],
			today,
		)
		self.assertEqual(len(found), 2)
		self.assertTrue(found[0]["rule_key"].startswith("ehs-hazard-review:HAZ-1"))
		self.assertIn("relies on ppe", found[1]["title"])

	def test_exposure(self):
		record = {
			"name": "EXP-1",
			"agent": "Respirable silica",
			"unit": "mg/m3",
			"result": 0.06,
			"limit": 0.05,
			"action_level": 0.025,
			"status": "Above Limit",
		}
		found = exposure_findings(record)
		self.assertEqual(found[0]["severity"], "Critical")
		self.assertEqual(exposure_findings({**record, "status": "Below Action Level"}), [])

	def test_serious_incidents(self):
		base = {"name": "SINC-1", "incident_type": "Near Miss", "occurred_on": START}
		self.assertEqual(serious_incident_findings(base), [])
		self.assertEqual(serious_incident_findings({**base, "potential_severity": 3}), [])
		sif = serious_incident_findings({**base, "potential_severity": 5})
		self.assertEqual(sif[0]["severity"], "Critical")
		self.assertIn("potential severity is 5", sif[0]["suggestion"])
		release = serious_incident_findings(
			{**base, "incident_type": "Environmental Release", "reportable_release": 1}
		)
		self.assertIn("notification deadline", release[0]["suggestion"])
		self.assertEqual(serious_incident_findings({**base, "recordable": 1, "status": "Closed"}), [])


if __name__ == "__main__":
	unittest.main()
