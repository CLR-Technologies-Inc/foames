# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Work instruction captures, step order, sign-offs and rules, without a site."""

import unittest

from foames.foames_mes.work_instructions import (
	StepError,
	allowed_run_transition,
	allowed_template_transition,
	can_record,
	can_sign_off,
	completion_gaps,
	current_step,
	estimated_minutes,
	evaluate_capture,
	failed_step_finding,
	parse_choices,
	progress,
	stalled_runs,
	validate_template_step,
)


def step(idx, capture="Confirm", **extra):
	values = {"idx": idx, "title": f"Step {idx}", "capture": capture}
	values.update(extra)
	return values


def torque(**extra):
	return step(
		2,
		"Number",
		has_lower_limit=1,
		lower_limit=40,
		has_upper_limit=1,
		upper_limit=45,
		unit="Nm",
		**extra,
	)


class TestTransitions(unittest.TestCase):
	def test_template_flow(self):
		self.assertTrue(allowed_template_transition(None, "Draft"))
		self.assertTrue(allowed_template_transition("Draft", "Released"))
		self.assertTrue(allowed_template_transition("Released", "Obsolete"))
		self.assertTrue(allowed_template_transition("Draft", "Obsolete"))
		self.assertFalse(allowed_template_transition("Released", "Draft"))
		self.assertFalse(allowed_template_transition("Obsolete", "Released"))
		self.assertFalse(allowed_template_transition("Obsolete", "Draft"))

	def test_run_flow(self):
		self.assertTrue(allowed_run_transition(None, "In Progress"))
		self.assertFalse(allowed_run_transition(None, "Completed"))
		self.assertTrue(allowed_run_transition("In Progress", "On Hold"))
		self.assertTrue(allowed_run_transition("On Hold", "In Progress"))
		self.assertTrue(allowed_run_transition("On Hold", "Aborted"))
		self.assertFalse(allowed_run_transition("On Hold", "Completed"))
		self.assertTrue(allowed_run_transition("In Progress", "Completed"))
		for final in ("Completed", "Aborted"):
			self.assertFalse(allowed_run_transition(final, "In Progress"))
			self.assertTrue(allowed_run_transition(final, final))


class TestCaptures(unittest.TestCase):
	def test_confirm(self):
		self.assertEqual(evaluate_capture(step(1))["result"], "Done")

	def test_pass_fail(self):
		self.assertEqual(evaluate_capture(step(1, "Pass/Fail"), "Pass")["result"], "Pass")
		self.assertEqual(evaluate_capture(step(1, "Pass/Fail"), "nok")["result"], "Fail")
		with self.assertRaises(StepError):
			evaluate_capture(step(1, "Pass/Fail"), "maybe")

	def test_number_within_limits_includes_the_limits(self):
		for value, expected in (
			(40, "Pass"),
			("45", "Pass"),
			(42.5, "Pass"),
			(39.9, "Fail"),
			(45.01, "Fail"),
		):
			out = evaluate_capture(torque(), value)
			self.assertEqual(out["result"], expected, value)
			self.assertEqual(out["value_number"], float(value))

	def test_number_one_sided_and_without_limits(self):
		self.assertEqual(
			evaluate_capture(step(1, "Number", has_lower_limit=1, lower_limit=0), -1)["result"], "Fail"
		)
		self.assertEqual(
			evaluate_capture(step(1, "Number", has_lower_limit=1, lower_limit=0), 9e9)["result"], "Pass"
		)
		# A limit value without its flag is no limit: Float fields store 0 when empty.
		self.assertEqual(evaluate_capture(step(1, "Number", upper_limit=0), 7)["result"], "Done")

	def test_number_rejects_non_numbers(self):
		for bad in (None, "", "abc", "nan", "inf"):
			with self.assertRaises(StepError, msg=repr(bad)):
				evaluate_capture(torque(), bad)

	def test_text_needs_text(self):
		self.assertEqual(evaluate_capture(step(1, "Text"), " LOT-42 ")["value_text"], "LOT-42")
		with self.assertRaises(StepError):
			evaluate_capture(step(1, "Text"), "  ")

	def test_choice_and_failing_answers(self):
		s = step(1, "Choice", choices="Clean\nScratched\nCracked", failing_choices="Cracked")
		self.assertEqual(evaluate_capture(s, "Clean")["result"], "Done")
		self.assertEqual(evaluate_capture(s, "Cracked")["result"], "Fail")
		with self.assertRaises(StepError):
			evaluate_capture(s, "Dirty")

	def test_parse_choices(self):
		self.assertEqual(parse_choices("A\n\n B \nA"), ["A", "B"])
		self.assertEqual(parse_choices("A, B ,C"), ["A", "B", "C"])
		self.assertEqual(parse_choices(None), [])


class TestTemplateSteps(unittest.TestCase):
	def test_valid_steps(self):
		self.assertEqual(validate_template_step(torque(post_measurement=1, measurement_name="torque")), [])
		self.assertEqual(validate_template_step(step(1)), [])

	def test_problems(self):
		self.assertTrue(
			validate_template_step(
				step(1, "Number", has_lower_limit=1, lower_limit=5, has_upper_limit=1, upper_limit=1)
			)
		)
		self.assertTrue(validate_template_step(step(1, "Choice", choices="Only")))
		self.assertTrue(validate_template_step(step(1, "Choice", choices="A\nB", failing_choices="C")))
		self.assertTrue(validate_template_step(step(1, "Text", post_measurement=1, measurement_name="x")))
		self.assertTrue(validate_template_step(torque(post_measurement=1)))
		self.assertTrue(validate_template_step(step(1, "Confirm", stop_on_fail=1)))
		self.assertTrue(validate_template_step(step(1, "Video")))


class TestOrderAndSignOff(unittest.TestCase):
	def steps(self):
		return [
			step(1, result="Done", completed_by="op@x"),
			torque(sign_off_role="FoaMES Quality"),
			step(3, optional=1),
			step(4),
		]

	def test_steps_go_in_order(self):
		steps = self.steps()
		can_record(steps, 2)
		with self.assertRaisesRegex(StepError, "comes first"):
			can_record(steps, 3)
		with self.assertRaisesRegex(StepError, "already recorded"):
			can_record(steps, 1)
		with self.assertRaisesRegex(StepError, "no step"):
			can_record(steps, 9)

	def test_sign_off_holds_the_next_step(self):
		steps = self.steps()
		steps[1].update(result="Pass", completed_by="op@x")
		self.assertEqual(current_step(steps)["idx"], 2)
		with self.assertRaisesRegex(StepError, "sign-off"):
			can_record(steps, 3)
		steps[1]["signed_off_by"] = "qa@x"
		can_record(steps, 3)
		self.assertEqual(current_step(steps)["idx"], 3)

	def test_only_optional_steps_can_be_skipped(self):
		steps = self.steps()
		steps[1].update(result="Pass", completed_by="op@x", signed_off_by="qa@x")
		can_record(steps, 3, skip=True)
		steps[2]["result"] = "Skipped"
		with self.assertRaisesRegex(StepError, "required"):
			can_record(steps, 4, skip=True)

	def test_two_person_rule(self):
		s = torque(sign_off_role="FoaMES Quality", result="Pass", completed_by="op@x")
		with self.assertRaisesRegex(StepError, "someone other"):
			can_sign_off(s, "op@x", ["FoaMES Quality"])
		with self.assertRaisesRegex(StepError, "must be signed off by FoaMES Quality"):
			can_sign_off(s, "sup@x", ["FoaMES Supervisor"])
		can_sign_off(s, "qa@x", ["FoaMES Quality"])
		with self.assertRaisesRegex(StepError, "not been recorded"):
			can_sign_off(torque(sign_off_role="FoaMES Quality"), "qa@x", ["FoaMES Quality"])
		with self.assertRaisesRegex(StepError, "needs no sign-off"):
			can_sign_off(step(1, result="Done"), "qa@x", ["FoaMES Quality"])
		with self.assertRaisesRegex(StepError, "already signed off"):
			can_sign_off({**s, "signed_off_by": "qa@x"}, "qa2@x", ["FoaMES Quality"])

	def test_completion_and_progress(self):
		steps = self.steps()
		self.assertEqual(len(completion_gaps(steps)), 3)
		steps[1].update(result="Fail", value_text="39", completed_by="op@x")
		steps[2]["result"] = "Skipped"
		steps[3]["result"] = "Done"
		self.assertEqual(
			completion_gaps(steps), ["Step 2 (Step 2) is waiting for a sign-off by FoaMES Quality"]
		)
		self.assertEqual(progress(steps)["done"], 3)
		self.assertEqual(progress(steps)["failed"], 1)
		steps[1]["signed_off_by"] = "qa@x"
		self.assertEqual(completion_gaps(steps), [])
		self.assertEqual(
			progress(steps), {"done": 4, "total": 4, "failed": 1, "current_idx": None, "current_title": None}
		)

	def test_estimate(self):
		self.assertEqual(
			estimated_minutes([step(1, estimated_minutes=2.5), step(2), step(3, estimated_minutes=None)]), 2.5
		)


class TestRules(unittest.TestCase):
	def test_failed_step_finding(self):
		run = {"name": "WIR-1", "work_instruction": "WI-A-REV01", "machine": "press-1"}
		f = failed_step_finding(run, torque(stop_on_fail=1, result="Fail", value_text="39"))
		self.assertEqual(f["rule_key"], "work-instruction:WIR-1:step:2:fail")
		self.assertEqual((f["category"], f["severity"]), ("Work Instruction", "Critical"))
		self.assertEqual(f["evidence"]["lower_limit"], 40.0)
		self.assertIn("on hold", f["suggestion"])
		self.assertEqual(failed_step_finding(run, torque(result="Fail"))["severity"], "Warning")

	def test_stalled_runs(self):
		def run(minutes, estimate=10, status="In Progress"):
			return {
				"name": "WIR-1",
				"work_instruction": "WI-A-REV01",
				"machine": "press-1",
				"status": status,
				"minutes_open": minutes,
				"estimated_minutes": estimate,
				"steps_done": 1,
				"steps_total": 4,
				"current_title": "Torque",
			}

		self.assertEqual(stalled_runs({"work_instruction_runs": [run(19)]}), [])
		# Twice the estimate but only 10 minutes over it: not yet.
		self.assertEqual(stalled_runs({"work_instruction_runs": [run(20)]}), [])
		out = stalled_runs({"work_instruction_runs": [run(26)]})
		self.assertEqual(out[0]["rule_key"], "work-instruction:WIR-1:stalled")
		self.assertIn("step 2 of 4 (Torque)", out[0]["suggestion"])
		self.assertEqual(stalled_runs({"work_instruction_runs": [run(500, estimate=0)]}), [])
		self.assertEqual(stalled_runs({"work_instruction_runs": [run(500, status="Completed")]}), [])
		self.assertEqual(stalled_runs({}), [])


if __name__ == "__main__":
	unittest.main()
