# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The pure implicit-validation evaluators: no site needed.

python -m unittest foames.foames_validation.test_implicit_logic
"""

import random
import unittest
from datetime import datetime, timedelta
from typing import ClassVar

from foames.foames_validation import implicit as iv

AS_OF = datetime(2026, 11, 16, 12, 0, 0)
START = AS_OF - timedelta(hours=2)
INSTRUMENT = {
	"id": "GAUGE-7",
	"calibrated_on": "2026-06-01",
	"calibration_due": "2027-06-01",
	"traceability": "CERT-2026-118",
}


def readings(values, step_seconds=60, start=START):
	return [
		{"t": (start + timedelta(seconds=i * step_seconds)).isoformat(), "v": v} for i, v in enumerate(values)
	]


def stable(n=40, mean=10.0, sd=0.02, seed=7):
	rng = random.Random(seed)
	return [round(rng.gauss(mean, sd), 5) for _ in range(n)]


def dataset(values=None, unit="mm", **series):
	return {
		"id": "DS-1",
		"measurements": {
			"bore": {
				"unit": unit,
				"instrument": INSTRUMENT,
				"points": readings(stable() if values is None else values),
				**series,
			}
		},
	}


def definition(*checks):
	return {"schema": iv.SCHEMA, "name": "Bore change", "version": "2", "checks": list(checks)}


def capability(**overrides):
	return {
		"key": "bore-cpk",
		"kind": "statistical",
		"measurement": "bore",
		"unit": "mm",
		"check_type": "Capability",
		"lower_limit": 9.9,
		"upper_limit": 10.1,
		"min_points": 25,
		**overrides,
	}


def metrology(**overrides):
	return {"key": "bore-msa", "kind": "metrology", "measurement": "bore", "unit": "mm", **overrides}


class TestDefinition(unittest.TestCase):
	def test_malformed_definitions_are_refused(self):
		for bad in (
			{},
			{"checks": []},
			{"schema": "other/9", "checks": [capability()]},
			definition({"kind": "statistical", "measurement": "bore"}),
			definition(capability(), capability()),
			definition({"key": "x", "kind": "guess"}),
			definition({"key": "x", "kind": "requirement", "assert": {"path": "a", "op": "approx"}}),
		):
			with self.assertRaises(iv.DefinitionError):
				iv.validate_definition(bad)

	def test_a_critical_check_cannot_be_made_advisory(self):
		checked = iv.validate_definition(definition(capability(criticality="Critical", blocking=False)))
		self.assertTrue(checked["checks"][0]["blocking"])

	def test_as_of_is_required(self):
		with self.assertRaises(iv.DefinitionError):
			iv.evaluate(definition(capability()), dataset(), None, None)


class TestRequirements(unittest.TestCase):
	CONFIG: ClassVar[dict] = {"gateway": {"security_mode": "SignAndEncrypt", "retry": 5, "hosts": ["a"]}}

	def judge(self, op, path, value=None, config=CONFIG):
		check = iv.validate_definition(
			definition(
				{"key": "r", "kind": "requirement", "assert": {"path": path, "op": op, "value": value}}
			)
		)["checks"][0]
		return iv.evaluate_requirement(check, config)["outcome"]

	def test_met_and_violated_requirements(self):
		self.assertEqual(self.judge("eq", "gateway.security_mode", "SignAndEncrypt"), iv.PASS)
		self.assertEqual(self.judge("le", "gateway.retry", 3), iv.FAIL)
		self.assertEqual(self.judge("in", "gateway.security_mode", ["Sign", "SignAndEncrypt"]), iv.PASS)
		self.assertEqual(self.judge("present", "gateway.hosts.0"), iv.PASS)
		self.assertEqual(self.judge("absent", "gateway.password"), iv.PASS)
		self.assertEqual(self.judge("absent", "gateway.retry"), iv.FAIL)

	def test_a_value_that_may_be_a_secret_is_not_recorded(self):
		config = {"gateway": {"password": "hunter2", "user": "svc"}}
		for op, extra in (("absent", {}), ("present", {"sensitive": True})):
			check = iv.validate_definition(
				definition(
					{
						"key": "r",
						"kind": "requirement",
						"assert": {"path": "gateway.password", "op": op},
						**extra,
					}
				)
			)["checks"][0]
			result = iv.evaluate_requirement(check, config)
			self.assertNotIn("hunter2", iv.canonical(result))

	def test_a_sensitive_path_is_never_compared_with_a_value(self):
		for op in ("eq", "ne", "in", "present", "absent"):
			with self.assertRaises(iv.DefinitionError):
				iv.validate_definition(
					definition(
						{
							"key": "r",
							"kind": "requirement",
							"assert": {"path": "gateway.password", "op": op, "value": "hunter2"},
							"sensitive": True,
						}
					)
				)

	def test_missing_configuration_is_indeterminate_never_pass(self):
		self.assertEqual(self.judge("eq", "gateway.certificate", "x"), iv.INDETERMINATE)
		self.assertEqual(self.judge("eq", "gateway.security_mode", "x", config=None), iv.INDETERMINATE)

	def test_a_non_number_against_a_bound_fails(self):
		self.assertEqual(self.judge("ge", "gateway.security_mode", 1), iv.FAIL)


class TestMetrology(unittest.TestCase):
	def judge(self, check=None, data=None, as_of=AS_OF):
		check = iv.validate_definition(definition(check or metrology()))["checks"][0]
		return iv.evaluate_metrology(check, data or dataset(), as_of)

	def parts(self, result):
		return {p["part"]: p["outcome"] for p in result["evidence"]["parts"]}

	def test_a_calibrated_traceable_measurement_passes(self):
		result = self.judge(metrology(max_interval_seconds=120, tolerance=0.1, uncertainty=0.01))
		self.assertEqual(result["outcome"], iv.PASS, result["summary"])

	def test_stale_calibration_fails(self):
		data = dataset()
		data["measurements"]["bore"]["instrument"] = {**INSTRUMENT, "calibration_due": "2026-10-01"}
		self.assertEqual(self.parts(self.judge(data=data))["calibration"], iv.FAIL)

	def test_no_calibration_record_is_indeterminate(self):
		data = dataset()
		data["measurements"]["bore"]["instrument"] = {}
		result = self.judge(data=data)
		self.assertEqual(self.parts(result)["calibration"], iv.INDETERMINATE)
		self.assertEqual(result["outcome"], iv.INDETERMINATE)

	def test_wrong_and_undeclared_units(self):
		self.assertEqual(self.parts(self.judge(data=dataset(unit="kg")))["unit"], iv.FAIL)
		self.assertEqual(self.parts(self.judge(data=dataset(unit=None)))["unit"], iv.INDETERMINATE)
		self.assertEqual(self.parts(self.judge(data=dataset(unit="um")))["unit"], iv.PASS)

	def test_unknown_time_is_indeterminate_and_disorder_fails(self):
		data = dataset()
		data["measurements"]["bore"]["points"][3]["t"] = None
		self.assertEqual(self.parts(self.judge(data=data))["time"], iv.INDETERMINATE)
		data = dataset()
		points = data["measurements"]["bore"]["points"]
		points[2], points[3] = points[3], points[2]
		self.assertEqual(self.parts(self.judge(data=data))["time"], iv.FAIL)
		future = dataset()
		future["measurements"]["bore"]["points"] = readings(stable(), start=AS_OF + timedelta(minutes=1))
		self.assertEqual(self.parts(self.judge(data=future))["time"], iv.INDETERMINATE)

	def test_sampling_gap_and_stale_data_fail(self):
		values = stable()
		points = readings(values[:20]) + readings(values[20:], start=START + timedelta(minutes=50))
		data = dataset()
		data["measurements"]["bore"]["points"] = points
		self.assertEqual(self.parts(self.judge(metrology(max_interval_seconds=120), data))["time"], iv.FAIL)
		self.assertEqual(self.parts(self.judge(metrology(max_age_seconds=60)))["freshness"], iv.FAIL)

	def test_uncertainty_bias_and_grr(self):
		self.assertEqual(
			self.parts(self.judge(metrology(tolerance=0.1, uncertainty=0.05)))["uncertainty"], iv.FAIL
		)
		self.assertEqual(self.parts(self.judge(metrology(tolerance=0.1)))["uncertainty"], iv.INDETERMINATE)
		self.assertEqual(
			self.parts(self.judge(metrology(reference_value=10.0, bias_limit=0.05)))["bias"], iv.PASS
		)
		self.assertEqual(
			self.parts(self.judge(metrology(reference_value=9.8, bias_limit=0.05)))["bias"], iv.FAIL
		)
		self.assertEqual(self.parts(self.judge(metrology(grr_percent=8)))["grr"], iv.PASS)
		self.assertEqual(self.parts(self.judge(metrology(grr_percent=20)))["grr"], iv.MANUAL)
		self.assertEqual(self.parts(self.judge(metrology(grr_percent=35)))["grr"], iv.FAIL)

	def test_data_side_numbers_are_compared_in_the_check_unit(self):
		# 0.05 mm of uncertainty is 50 um: a 100 um tolerance gives a ratio of 2, not 2000.
		check = metrology(unit="um", tolerance=100)
		self.assertEqual(
			self.parts(self.judge(check, dataset(unit="mm", uncertainty=0.05)))["uncertainty"], iv.FAIL
		)
		self.assertEqual(
			self.parts(self.judge(check, dataset(unit="mm", uncertainty=0.01)))["uncertainty"], iv.PASS
		)
		# Readings in um against a reference and a bias limit in mm.
		micrometres = [v * 1000 for v in stable()]
		bias = metrology(unit="mm", reference_value=10.0, bias_limit=0.05)
		self.assertEqual(self.parts(self.judge(bias, dataset(micrometres, unit="um")))["bias"], iv.PASS)

	def test_offsets_are_compared_in_utc(self):
		# 12:00-05:00 is 17:00 UTC, after an evaluation at 12:00 UTC.
		data = dataset()
		data["measurements"]["bore"]["points"] = readings(stable(), start=AS_OF.replace(hour=11))
		for point in data["measurements"]["bore"]["points"]:
			point["t"] += "-05:00"
		self.assertEqual(self.parts(self.judge(data=data))["time"], iv.INDETERMINATE)

	def test_no_data_is_indeterminate(self):
		self.assertEqual(self.judge(metrology(measurement="torque"))["outcome"], iv.INDETERMINATE)


class TestStatistics(unittest.TestCase):
	def judge(self, check=None, data=None):
		check = iv.validate_definition(definition(check or capability()))["checks"][0]
		return iv.evaluate_statistical(check, data or dataset())

	def test_capable_process_passes(self):
		self.assertEqual(self.judge()["outcome"], iv.PASS)

	def test_too_much_variation_fails(self):
		self.assertEqual(self.judge(data=dataset(stable(sd=0.06)))["outcome"], iv.FAIL)

	def test_insufficient_samples_are_indeterminate(self):
		self.assertEqual(self.judge(data=dataset(stable(n=10)))["outcome"], iv.INDETERMINATE)

	def test_out_of_control_point_fails_control_but_capability_is_a_separate_check(self):
		values = stable()
		values[30] = 10.09  # inside the specification, far outside the control limits
		control = capability(key="bore-control", check_type="Statistical Control")
		self.assertEqual(self.judge(control, dataset(values))["outcome"], iv.FAIL)

	def test_bounds(self):
		bounds = capability(key="bore-range", check_type="Numeric Range")
		self.assertEqual(self.judge(bounds)["outcome"], iv.PASS)
		values = stable()
		values[5] = 10.2
		self.assertEqual(self.judge(bounds, dataset(values))["outcome"], iv.FAIL)

	def test_values_are_converted_and_wrong_units_fail(self):
		micrometres = [v * 1000 for v in stable()]
		self.assertEqual(self.judge(data=dataset(micrometres, unit="um"))["outcome"], iv.PASS)
		self.assertEqual(self.judge(data=dataset(unit="degC"))["outcome"], iv.FAIL)
		self.assertEqual(self.judge(data=dataset(unit=None))["outcome"], iv.INDETERMINATE)

	def test_drift_from_baseline_fails(self):
		self.assertEqual(self.judge(capability(baseline_mean=9.95, max_shift=0.02))["outcome"], iv.FAIL)
		self.assertEqual(self.judge(capability(baseline_mean=10.0, max_shift=0.02))["outcome"], iv.PASS)


class TestRun(unittest.TestCase):
	CONFIG: ClassVar[dict] = {"spindle": {"max_rpm": 8000}}

	def run_it(self, *checks, data=None, config=CONFIG, revision="rev-1", environment="Sandbox"):
		return iv.evaluate(definition(*checks), data or dataset(), config, AS_OF, revision, environment)

	def test_fails_closed_on_a_blocking_indeterminate_check(self):
		result = self.run_it(capability(), capability(key="thin", min_points=500))
		self.assertEqual(result["outcome"], iv.INDETERMINATE)

	def test_a_non_blocking_check_is_a_warning(self):
		result = self.run_it(capability(), capability(key="thin", min_points=500, blocking=False))
		self.assertEqual(result["outcome"], iv.PASS)
		self.assertEqual(result["warnings"], ["thin"])

	def test_manual_review_is_explicit(self):
		result = self.run_it(
			capability(), {"key": "visual", "kind": "manual", "description": "Inspect the fixture"}
		)
		self.assertEqual(result["outcome"], iv.MANUAL)
		self.assertEqual(result["manual_review"], ["visual"])

	def test_a_violated_requirement_fails_the_run(self):
		requirement = {
			"key": "rpm",
			"kind": "requirement",
			"assert": {"path": "spindle.max_rpm", "op": "le", "value": 6000},
		}
		self.assertEqual(self.run_it(capability(), requirement)["outcome"], iv.FAIL)

	def test_evidence_is_reproducible_and_pinned_to_the_revision(self):
		first, second = self.run_it(capability()), self.run_it(capability())
		self.assertEqual(first["input_hash"], second["input_hash"])
		self.assertEqual(first["result_hash"], second["result_hash"])
		self.assertTrue(iv.verify_bundle(first))
		other = self.run_it(capability(), revision="rev-2")
		self.assertNotEqual(other["input_hash"], first["input_hash"])
		self.assertEqual(other["configuration"]["revision"], "rev-2")

	def test_same_criteria_on_sandbox_and_candidate_production(self):
		sandbox = self.run_it(capability(), environment="Sandbox")
		candidate = self.run_it(capability(), environment="Production Candidate")
		self.assertEqual(sandbox["definition"]["hash"], candidate["definition"]["hash"])
		self.assertEqual(sandbox["outcome"], candidate["outcome"])
		self.assertNotEqual(sandbox["input_hash"], candidate["input_hash"])

	def test_non_finite_numbers_are_refused(self):
		with self.assertRaises(ValueError):
			self.run_it(capability(), data=dataset([float("nan")] * 30))

	def test_a_changed_bundle_no_longer_verifies(self):
		bundle = self.run_it(capability(), data=dataset(stable(sd=0.06)))
		self.assertEqual(bundle["outcome"], iv.FAIL)
		bundle["outcome"] = iv.PASS
		self.assertFalse(iv.verify_bundle(bundle))


class TestUnits(unittest.TestCase):
	def test_conversions(self):
		self.assertAlmostEqual(iv.convert(1, "in", "mm"), 25.4)
		self.assertAlmostEqual(iv.convert(100, "degC", "degF"), 212)
		self.assertAlmostEqual(iv.convert(0, "°C", "K"), 273.15)
		with self.assertRaises(ValueError):
			iv.convert(1, "mm", "kg")
		with self.assertRaises(ValueError):
			iv.convert(1, "furlong", "mm")


if __name__ == "__main__":
	unittest.main()
