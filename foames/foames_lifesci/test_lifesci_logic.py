# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Life-sciences rules and arithmetic: stage gates, requirement tracing, tech transfer checks,
comparability, designed experiments, response-surface fits, what-if and scale-up. No Frappe site
needed."""

import math
import unittest
from datetime import date

from foames.foames_lifesci import doe, npi, requirements, scaleup, stats, transfer


class TestStats(unittest.TestCase):
	def test_t_quantiles_match_tables(self):
		# Two-sided 95 % and one-sided 95 % critical values from standard t tables.
		self.assertAlmostEqual(stats.t_ppf(0.975, 5), 2.5706, places=4)
		self.assertAlmostEqual(stats.t_ppf(0.95, 10), 1.8125, places=4)
		self.assertAlmostEqual(stats.t_ppf(0.975, 30), 2.0423, places=4)
		self.assertAlmostEqual(stats.t_ppf(0.025, 5), -2.5706, places=4)
		self.assertAlmostEqual(stats.t_cdf(0.0, 7), 0.5)

	def test_summaries(self):
		self.assertAlmostEqual(stats.stdev([2, 4, 4, 4, 5, 5, 7, 9]), 2.13809, places=5)
		self.assertEqual(stats.percentile([1, 2, 3, 4, 5], 50), 3)
		self.assertEqual(stats.stdev([3.0]), 0.0)

	def test_solver(self):
		self.assertEqual([round(v, 9) for v in stats.solve([[2, 1], [1, 3]], [3, 5])], [0.8, 1.4])
		with self.assertRaises(ValueError):
			stats.solve([[1, 2], [2, 4]], [1, 2])


def deliverable(stage, name, status="Not Started", required=True):
	return {"stage": stage, "deliverable": name, "status": status, "required": required}


class TestStageGates(unittest.TestCase):
	def test_templates_cover_every_stage(self):
		for product_type in ("Medical Device", "Biologic", "Drug Product", "Combination Product"):
			stages = {row[0] for row in npi.template_for(product_type)}
			self.assertEqual(stages, set(npi.STAGES), product_type)
		combo = [row[1] for row in npi.template_for("Combination Product")]
		self.assertEqual(len(combo), len(set(combo)))
		self.assertIn("Design history file complete", combo)
		self.assertIn("Tech transfer package approved", combo)

	def test_go_needs_required_deliverables(self):
		rows = [
			deliverable("Concept", "User needs", "Complete"),
			deliverable("Concept", "Plan", "In Progress"),
			deliverable("Concept", "Nice to have", "Not Started", required=False),
			deliverable("Feasibility", "PRD"),
		]
		problems = npi.decision_problems(
			program_status="Active",
			current_stage="Concept",
			gate_stage="Concept",
			decision="Go",
			deliverables=rows,
		)
		self.assertEqual(len(problems), 1)
		self.assertIn("Plan", problems[0])
		rows[1]["status"] = "Not Applicable"
		self.assertEqual(
			npi.decision_problems(
				program_status="Active",
				current_stage="Concept",
				gate_stage="Concept",
				decision="Go",
				deliverables=rows,
			),
			[],
		)

	def test_conditional_go_hold_and_independence(self):
		common = {"program_status": "Active", "current_stage": "Development", "deliverables": []}
		problems = npi.decision_problems(gate_stage="Development", decision="Conditional Go", **common)
		self.assertEqual(len(problems), 2)
		self.assertTrue(
			npi.decision_problems(gate_stage="Development", decision="Hold", **common)[0].startswith("A Hold")
		)
		self.assertIn(
			"Only the gate of the current stage",
			npi.decision_problems(gate_stage="Concept", decision="Kill", conditions="x", **common)[0],
		)
		self.assertIn(
			"program lead",
			npi.decision_problems(
				gate_stage="Development", decision="Go", decided_by="a@x", program_lead="a@x", **common
			)[0],
		)
		closed = {**common, "program_status": "Launched"}
		self.assertTrue(npi.decision_problems(gate_stage="Development", decision="Go", **closed))

	def test_apply_decision(self):
		self.assertEqual(npi.apply_decision("Concept", "Go"), ("Feasibility", "Active"))
		self.assertEqual(npi.apply_decision("Transfer", "Conditional Go"), ("Launch", "Active"))
		self.assertEqual(npi.apply_decision("Launch", "Go"), ("Launch", "Launched"))
		self.assertEqual(npi.apply_decision("Development", "Recycle"), ("Development", "Active"))
		self.assertEqual(npi.apply_decision("Development", "Hold"), ("Development", "On Hold"))
		self.assertEqual(npi.apply_decision("Development", "Kill"), ("Development", "Cancelled"))

	def test_gate_findings(self):
		program = {"name": "NPI-1", "title": "Pump", "status": "Active", "current_stage": "Feasibility"}
		gates = [
			{
				"stage": "Concept",
				"decision": "Conditional Go",
				"conditions": "Close CAPA",
				"conditions_due": date(2026, 11, 1),
			},
			{"stage": "Feasibility", "target_date": date(2026, 11, 20)},
		]
		rows = [deliverable("Feasibility", "PRD")]
		found = npi.gate_findings(program, gates, rows, date(2026, 11, 15))
		keys = sorted(f["rule_key"] for f in found)
		self.assertEqual(
			keys, ["npi-conditions:NPI-1:Concept:2026-11-01", "npi-gate:NPI-1:Feasibility:2026-11-20"]
		)
		# Far from the date with nothing overdue: no gate finding; closed conditions: none either.
		gates[0]["conditions_closed"] = 1
		self.assertEqual(npi.gate_findings(program, gates, rows, date(2026, 10, 1)), [])
		self.assertEqual(
			npi.gate_findings({**program, "status": "Cancelled"}, gates, rows, date(2027, 1, 1)), []
		)
		overdue = npi.gate_findings(program, gates, [], date(2026, 11, 25))
		self.assertEqual(overdue[0]["severity"], "Warning")


def req(rid, level, parent=None, **values):
	return {"req_id": rid, "level": level, "parent_req": parent, **values}


class TestRequirements(unittest.TestCase):
	def test_structure(self):
		rows = [
			req("UN-1", "User Need"),
			req("DI-1", "Design Input", "UN-1"),
			req("DI-1", "Design Input", "UN-1"),
			req("DI-2", "Design Input", "DI-1"),
			req("UN-2", "User Need", "UN-1"),
			req("CQA-1", "CQA", "QT-9"),
			req("1bad", "CQA"),
		]
		problems = requirements.requirement_problems(rows)
		text = " | ".join(problems)
		self.assertIn("DI-1 is used twice", text)
		self.assertIn("DI-2: a Design Input refines", text)
		self.assertIn("UN-2: a User Need is a top-level requirement", text)
		self.assertIn("CQA-1: parent QT-9 is not in this document", text)
		self.assertIn("'1bad'", text)
		self.assertEqual(
			requirements.requirement_problems([req("QT-1", "QTPP Element"), req("CQA-1", "CQA", "QT-1")]), []
		)

	def test_trace_matrix(self):
		rows = [
			req("UN-1", "User Need", validation_reference="VAL-1"),
			req("UN-2", "User Need", critical=1),
			req(
				"DI-1",
				"Design Input",
				"UN-1",
				acceptance_criteria="<= 5 N",
				verification_method="Test",
				design_output="DWG-7",
				verification_status="Passed",
			),
			req("DI-2", "Design Input", "UN-1", critical=1, verification_status="Failed"),
		]
		trace = requirements.trace_matrix(rows)
		self.assertEqual(trace["verifiable"], 2)
		self.assertEqual(trace["verified"], 1)
		self.assertEqual(trace["percent_verified"], 50.0)
		self.assertEqual(trace["percent_refined"], 50.0)
		self.assertEqual(trace["failed"], ["DI-2"])
		self.assertEqual(sorted(trace["critical_open"]), ["DI-2", "UN-2"])
		by_id = {m["req_id"]: m for m in trace["matrix"]}
		self.assertEqual(by_id["UN-1"]["children"], ["DI-1", "DI-2"])
		self.assertEqual(by_id["DI-1"]["gaps"], [])
		self.assertIn("no design output", by_id["DI-2"]["gaps"])


def cpp(name="Temperature", **values):
	row = {
		"parameter": name,
		"criticality": "CPP",
		"limits": "Lower and Upper",
		"set_point": 37.0,
		"nor_low": 36.5,
		"nor_high": 37.5,
		"par_low": 35.0,
		"par_high": 39.0,
	}
	row.update(values)
	return row


def cqa(name="Purity", **values):
	row = {
		"attribute": name,
		"criticality": "CQA",
		"limits": "Lower Only",
		"lower": 95.0,
		"approach": "Equivalence (TOST)",
		"margin": 1.0,
		"analytical_method": "HPLC-01",
	}
	row.update(values)
	return row


class TestTransferPackage(unittest.TestCase):
	def test_consistent_package(self):
		self.assertEqual(transfer.package_problems([cpp()], [cqa()]), [])

	def test_ranges_and_rules(self):
		problems = transfer.package_problems(
			[
				cpp(nor_low=34.0),
				cpp("pH", set_point=8.0, nor_low=6.9, nor_high=7.1, par_low=6.8, par_high=7.2),
				cpp("DO", limits="None"),
				cpp("Agitation", scale_dependent=1, scale_rule=None),
				cpp("Feed", scale_rule="Other (Justify)"),
				cpp("Temperature"),
			],
			[
				cqa(margin=0),
				cqa("Aggregates", criticality="Non-critical", limits="Lower and Upper", lower=5, upper=1),
			],
		)
		text = " | ".join(problems)
		for expected in (
			"The parameter Temperature is listed twice",
			"NOR must lie inside the PAR (NOR low 34.0 < PAR low 35.0)",
			"pH: the set point 8.0 is outside the NOR",
			"DO: a CPP needs a normal operating range",
			"Agitation: a scale-dependent parameter needs a scale rule",
			"Feed: an 'Other' scale rule needs a justification",
			"Purity: equivalence testing needs a positive equivalence margin",
			"Aggregates: the lower limit is above the upper limit",
		):
			self.assertIn(expected, text)
		self.assertIn("The package names no critical quality attribute", transfer.package_problems([], []))

	def test_scale_helpers(self):
		self.assertEqual(transfer.scale_ratio(200, 2000), 10)
		self.assertIsNone(transfer.scale_ratio(0, 2000))
		self.assertEqual(transfer.scale_set_point(1.5, "Linear with Volume", 10), 15)
		self.assertEqual(transfer.scale_set_point(0.1, "Constant vvm", 10), 0.1)
		self.assertIsNone(transfer.scale_set_point(300, "Constant P/V", 10))


class TestComparability(unittest.TestCase):
	sending = (98.1, 99.0, 98.5, 98.7, 98.4)
	receiving = (98.4, 98.9, 98.2, 98.6)

	def test_equivalence(self):
		result = transfer.assess_comparability(self.sending, self.receiving, "Equivalence (TOST)", margin=1.0)
		self.assertEqual(result["outcome"], "Comparable")
		self.assertEqual(result["interval"]["confidence"], 90.0)
		self.assertLess(result["interval"]["low"], 0)
		tight = transfer.assess_comparability(self.sending, self.receiving, "Equivalence (TOST)", margin=0.2)
		self.assertEqual(tight["outcome"], "Not Comparable")

	def test_equivalence_by_hand(self):
		# Welch interval computed independently: diff, se and df from the textbook formulas.
		s, r = [10.0, 12.0, 11.0], [11.0, 13.0, 12.0, 12.0]
		res = transfer.assess_comparability(s, r, "Equivalence (TOST)", margin=3.0)
		se = math.sqrt(1.0 / 3 + (2.0 / 3) / 4)
		df = se**4 / ((1.0 / 3) ** 2 / 2 + ((2.0 / 3) / 4) ** 2 / 3)
		half = stats.t_ppf(0.95, df) * se
		self.assertAlmostEqual(res["interval"]["low"], 1.0 - half, places=9)
		self.assertAlmostEqual(res["interval"]["df"], df, places=9)

	def test_quality_range_min_max_descriptive(self):
		qr = transfer.assess_comparability(self.sending, [*self.receiving, 90.0], "Quality Range", k=3)
		self.assertEqual(qr["interval"]["inside_percent"], 80.0)
		self.assertEqual(qr["outcome"], "Not Comparable")
		self.assertEqual(
			transfer.assess_comparability(
				self.sending, [*self.receiving, 90.0], "Quality Range", coverage=80
			)["outcome"],
			"Comparable",
		)
		mm = transfer.assess_comparability(self.sending, [98.2, 99.1], "Min-Max")
		self.assertEqual(mm["outcome"], "Not Comparable")
		self.assertEqual(
			transfer.assess_comparability(self.sending, self.receiving, "Descriptive")["outcome"],
			"Descriptive Only",
		)

	def test_out_of_spec_and_insufficient(self):
		oos = transfer.assess_comparability(
			self.sending, self.receiving, "Min-Max", limits="Lower Only", lower=98.3
		)
		self.assertEqual(oos["outcome"], "Not Comparable")
		self.assertEqual(oos["out_of_spec"], [98.2])
		self.assertEqual(
			transfer.assess_comparability([98.0], self.receiving, "Equivalence (TOST)", margin=1)["outcome"],
			"Insufficient Data",
		)
		self.assertEqual(
			transfer.assess_comparability(self.sending, [98.0], "Equivalence (TOST)", margin=1)["outcome"],
			"Insufficient Data",
		)
		with self.assertRaises(ValueError):
			transfer.assess_comparability(self.sending, self.receiving, "Vibes")


class TestDesigns(unittest.TestCase):
	def test_full_factorial(self):
		runs = doe.full_factorial(3)
		self.assertEqual(len(runs), 8)
		self.assertEqual(runs[0], [-1.0, -1.0, -1.0])
		self.assertEqual(runs[1], [1.0, -1.0, -1.0])  # standard order: first factor fastest
		self.assertEqual(len(doe.full_factorial(2, levels=3)), 9)

	def test_fractional_factorial_is_balanced_and_orthogonal(self):
		for (k, p), (_gens, resolution) in doe.GENERATORS.items():
			runs, res = doe.fractional_factorial(k, p)
			self.assertEqual(res, resolution)
			self.assertEqual(len(runs), 2 ** (k - p))
			for i in range(k):
				self.assertEqual(sum(r[i] for r in runs), 0)
				for j in range(i + 1, k):
					self.assertEqual(sum(r[i] * r[j] for r in runs), 0, (k, p, i, j))
		with self.assertRaises(ValueError):
			doe.fractional_factorial(4, 2)

	def test_central_composite_and_build(self):
		runs, kinds, alpha = doe.central_composite(3, rotatable=True)
		self.assertAlmostEqual(alpha, 8**0.25)
		self.assertEqual(len(runs), 8 + 6)
		self.assertEqual(kinds.count("Axial"), 6)
		d = doe.build_design("Central Composite (Face-Centred)", 2, center_points=3, replicates=2, seed=7)
		self.assertEqual(len(d["runs"]), (4 + 4) * 2 + 3)
		self.assertEqual([r["run_no"] for r in d["runs"]], list(range(1, 20)))
		self.assertEqual(sorted(r["std_order"] for r in d["runs"]), list(range(1, 20)))
		again = doe.build_design("Central Composite (Face-Centred)", 2, center_points=3, replicates=2, seed=7)
		self.assertEqual(d, again)
		with self.assertRaises(ValueError):
			doe.build_design("Full Factorial", 7)

	def test_coding(self):
		self.assertEqual(doe.coded(35, 30, 40), 0)
		self.assertEqual(doe.coded(40, 30, 40), 1)
		self.assertEqual(doe.actual(-1, 30, 40), 30)


class TestModels(unittest.TestCase):
	def setUp(self):
		design = doe.build_design("Central Composite (Face-Centred)", 2, center_points=3, randomise=False)
		self.points = [r["coded"] for r in design["runs"]]

		def truth(p):
			return 10 + 2 * p[0] - 1.5 * p[1] + 0.5 * p[0] * p[1] - p[0] ** 2

		self.y = [truth(p) for p in self.points]

	def test_quadratic_recovers_exact_coefficients(self):
		fit = doe.fit(self.points, self.y, "Quadratic", ["T", "pH"])
		estimates = {c["term"]: round(c["estimate"], 9) for c in fit["coefficients"]}
		self.assertEqual(
			estimates, {"Intercept": 10.0, "T": 2.0, "pH": -1.5, "T*pH": 0.5, "T^2": -1.0, "pH^2": 0.0}
		)
		self.assertAlmostEqual(fit["r_squared"], 1.0)
		self.assertAlmostEqual(doe.predict(fit, [0.5, -0.5]), 10 + 1 + 0.75 - 0.125 - 0.25)

	def test_noise_gives_errors_and_p_values(self):
		noisy = [y + (0.1 if i % 2 else -0.1) for i, y in enumerate(self.y)]
		fit = doe.fit(self.points, noisy, "Linear + Interactions")
		self.assertGreater(fit["rmse"], 0)
		self.assertLess(fit["r_squared"], 1)
		main = next(c for c in fit["coefficients"] if c["term"] == "x1")
		self.assertLess(main["p_value"], 0.01)

	def test_too_few_runs_or_aliased(self):
		with self.assertRaises(ValueError):
			doe.fit(self.points[:4], self.y[:4], "Quadratic")
		runs, _ = doe.fractional_factorial(3, 1)
		with self.assertRaises(ValueError):
			doe.fit(runs * 2, [1.0] * 8, "Linear + Interactions")

	def test_what_if_and_design_space(self):
		fit = doe.fit(self.points, self.y, "Quadratic", ["T", "pH"])
		factors = [
			{"name": "T", "low": 30, "high": 40, "nominal": 35, "distribution": "Normal", "sd": 0.5},
			{"name": "pH", "low": 6.8, "high": 7.4, "nominal": 7.1, "distribution": "Fixed"},
		]
		responses = [{"name": "titer", "limits": "Lower Only", "lower": 9.5}]
		one = doe.what_if(factors, responses, {"titer": fit}, iterations=800, seed=3)
		two = doe.what_if(factors, responses, {"titer": fit}, iterations=800, seed=3)
		self.assertEqual(one, two)
		r = one["responses"][0]
		self.assertAlmostEqual(r["mean"], 10.0, delta=0.05)
		self.assertGreater(r["probability_in_limits"], 0.99)
		self.assertIsNotNone(r["predicted_ppk"])
		space = doe.design_space(factors, responses, {"titer": fit}, 0, 1, steps=5)
		self.assertEqual(len(space["grid"]), 5)
		self.assertEqual(space["grid"][0][2], 1)  # centre of T, low pH: 10 + 1.5 = 11.5
		self.assertEqual(space["grid"][4][0], 0)  # low T, high pH: 10 - 2 - 1.5 - 0.5 - 1 = 5
		self.assertLess(space["percent_inside"], 100)
		with self.assertRaises(ValueError):
			doe.what_if(factors, responses, {}, iterations=10)


class TestScaleUp(unittest.TestCase):
	def test_criteria(self):
		s = scaleup.scale_up(
			small_volume_l=2,
			large_volume_l=2000,
			impeller_diameter_m=0.05,
			rpm=300,
			tank_diameter_m=0.13,
			gas_l_min=0.2,
		)
		self.assertAlmostEqual(s["length_ratio"], 10.0)
		large = {row["criterion"]: row for row in s["large"]}
		self.assertAlmostEqual(large["Constant P/V"]["ratios"]["p_per_v_w_m3"], 1.0)
		self.assertAlmostEqual(large["Constant Tip Speed"]["ratios"]["tip_speed_m_s"], 1.0)
		self.assertAlmostEqual(large["Constant Reynolds"]["ratios"]["reynolds"], 1.0)
		self.assertAlmostEqual(large["Constant Mixing Time"]["rpm"], 300)
		self.assertAlmostEqual(large["Constant P/V"]["rpm"], 300 * 10 ** (-2 / 3))
		# Constant vvm: gas flow follows volume, so superficial velocity rises with the length ratio.
		self.assertAlmostEqual(large["Constant P/V"]["vvm"], s["small"]["vvm"])
		self.assertAlmostEqual(
			large["Constant P/V"]["superficial_velocity_m_s"] / s["small"]["superficial_velocity_m_s"], 10.0
		)
		self.assertAlmostEqual(large["Constant P/V"]["ratios"]["kla_per_h"], 10**0.5)

	def test_power_and_validation(self):
		state = scaleup.state(1000, 0.3, 120, 5.0, 1000, 0.001)
		self.assertAlmostEqual(state["power_w"], 5 * 1000 * 2**3 * 0.3**5)
		self.assertAlmostEqual(state["reynolds"], 1000 * 2 * 0.09 / 0.001)
		with self.assertRaises(ValueError):
			scaleup.scale_up(small_volume_l=0, large_volume_l=10, impeller_diameter_m=0.1, rpm=100)
		with self.assertRaises(ValueError):
			scaleup.scale_up(
				small_volume_l=1, large_volume_l=10, impeller_diameter_m=0.1, rpm=100, gas_rule="Sideways"
			)
		vs_rule = scaleup.scale_up(
			small_volume_l=2,
			large_volume_l=2000,
			impeller_diameter_m=0.05,
			rpm=300,
			tank_diameter_m=0.13,
			gas_l_min=0.2,
			gas_rule="Constant Superficial Gas Velocity",
		)
		self.assertAlmostEqual(
			vs_rule["large"][0]["superficial_velocity_m_s"], vs_rule["small"]["superficial_velocity_m_s"]
		)


if __name__ == "__main__":
	unittest.main()
