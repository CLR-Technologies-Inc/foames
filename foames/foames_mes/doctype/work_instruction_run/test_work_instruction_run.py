# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Work Instruction and Work Instruction Run on a site: revisions and release, starting a run,
recording steps in order, the two-person sign-off, holds, measurements for SPC, failed-step and
stalled-run suggestions, and the floor snapshot."""

import frappe
from frappe.utils import add_to_date, now_datetime

from foames.foames_mes.doctype.work_instruction.work_instruction import (
	list_instructions_for_machine,
	new_revision,
	release,
)
from foames.foames_mes.doctype.work_instruction_run.work_instruction_run import (
	abort_run,
	complete_run,
	get_run,
	list_active_runs,
	record_step,
	release_hold,
	sign_off_step,
	start_run,
)
from foames.foames_mes.floor import collect_findings, floor_snapshot
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user

OPERATOR = "wi-operator@example.com"
SUPERVISOR = "wi-supervisor@example.com"


def make_instruction(code="T-WI-CHANGE", released=True, **overrides):
	values = {
		"doctype": "Work Instruction",
		"instruction_code": code,
		"title": "Press changeover",
		"operation": "Changeover",
		"safety_notes": "Lock out the press before reaching in.",
		"steps": [
			{"title": "Lock out the press", "capture": "Confirm", "estimated_minutes": 2},
			{
				"title": "Torque the die clamps",
				"capture": "Number",
				"unit": "Nm",
				"has_lower_limit": 1,
				"lower_limit": 40,
				"has_upper_limit": 1,
				"upper_limit": 45,
				"post_measurement": 1,
				"measurement_name": "clamp_torque",
				"sign_off_role": "FoaMES Quality",
				"estimated_minutes": 5,
			},
			{"title": "Photo of the die", "capture": "Confirm", "optional": 1},
			{
				"title": "First part visual check",
				"capture": "Pass/Fail",
				"stop_on_fail": 1,
				"estimated_minutes": 3,
			},
		],
	}
	values.update(overrides)
	doc = frappe.get_doc(values).insert()
	if released:
		release(doc.name)
		doc.reload()
	return doc


class TestWorkInstruction(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-WI-PRESS", machine_type="T-WI-Press")
		make_machine("T-WI-LATHE", machine_type="T-WI-Lathe")
		make_user(OPERATOR, "FoaMES Operator")
		make_user(SUPERVISOR, "FoaMES Supervisor")

	def test_revision_name_estimate_and_release(self):
		doc = make_instruction(released=False)
		self.assertEqual((doc.name, doc.revision, doc.status), ("T-WI-CHANGE-REV01", 1, "Draft"))
		self.assertEqual(doc.estimated_minutes, 10)
		release(doc.name)
		doc.reload()
		self.assertEqual(doc.status, "Released")
		self.assertTrue(doc.released_at and doc.released_by)

	def test_released_revision_is_frozen_and_new_revision_supersedes_it(self):
		doc = make_instruction()
		doc.steps[1].upper_limit = 50
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.title = "Changed"
		self.assertRaises(frappe.ValidationError, doc.save)
		out = new_revision(doc.name, "Wider torque window")
		self.assertEqual(out["name"], "T-WI-CHANGE-REV02")
		draft = frappe.get_doc("Work Instruction", out["name"])
		self.assertEqual((draft.status, draft.amended_from_revision), ("Draft", doc.name))
		draft.steps[1].upper_limit = 50
		draft.save()
		release(draft.name)
		self.assertEqual(frappe.db.get_value("Work Instruction", doc.name, "status"), "Obsolete")
		self.assertEqual(frappe.db.get_value("Work Instruction", draft.name, "status"), "Released")

	def test_supervisor_cannot_release(self):
		doc = make_instruction(released=False)
		with as_user(SUPERVISOR):
			# Supervisors can read but not write instructions, let alone release them.
			self.assertRaises(frappe.PermissionError, release, doc.name)

	def test_bad_steps_are_refused(self):
		self.assertRaises(
			frappe.ValidationError,
			make_instruction,
			code="T-WI-BAD",
			released=False,
			steps=[{"title": "Pick", "capture": "Choice", "choices": "Only one"}],
		)

	def test_instructions_offered_at_a_machine(self):
		make_instruction("T-WI-ALL")
		make_instruction("T-WI-PRESSES", machine_type="T-WI-Press")
		make_instruction("T-WI-THIS", machine="T-WI-PRESS")
		make_instruction("T-WI-DRAFT", released=False)
		codes = [r.instruction_code for r in list_instructions_for_machine("T-WI-PRESS")]
		self.assertEqual(codes[:2], ["T-WI-THIS", "T-WI-PRESSES"])
		self.assertIn("T-WI-ALL", codes)
		self.assertNotIn("T-WI-DRAFT", codes)
		lathe = [r.instruction_code for r in list_instructions_for_machine("T-WI-LATHE")]
		self.assertNotIn("T-WI-THIS", lathe)
		self.assertNotIn("T-WI-PRESSES", lathe)


class TestWorkInstructionRun(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-WI-PRESS", machine_type="T-WI-Press")
		make_user(OPERATOR, "FoaMES Operator")
		make_user(SUPERVISOR, "FoaMES Supervisor")
		self.instruction = make_instruction()

	def start(self):
		with as_user(OPERATOR):
			return start_run(self.instruction.name, "T-WI-PRESS")

	def test_full_run_with_sign_off_and_measurement(self):
		run = self.start()
		self.assertEqual((run["status"], run["current_step"], run["revision"]), ("In Progress", 1, 1))
		self.assertEqual(len(run["steps"]), 4)
		name = run["name"]
		with as_user(OPERATOR):
			self.assertRaises(frappe.ValidationError, record_step, name, 2, 42)  # step 1 first
			record_step(name, 1)
			run = record_step(name, 2, "42.5", note="all four clamps")
			self.assertEqual(run["steps"][1]["result"], "Pass")
			# Step 2 waits for its sign-off, and the operator cannot sign their own step.
			self.assertRaises(frappe.ValidationError, record_step, name, 3)
			self.assertRaises(frappe.ValidationError, sign_off_step, name, 2)
		event = run["steps"][1]["machine_event"]
		self.assertTrue(event)
		self.assertEqual(
			frappe.db.get_value(
				"Machine Event", event, ["event_type", "measurement_name", "value", "source"]
			),
			("Measurement", "clamp_torque", 42.5, "Manual"),
		)
		run = sign_off_step(name, 2)  # Administrator holds FoaMES Quality
		self.assertEqual(run["steps"][1]["signed_off_by"], "Administrator")
		with as_user(OPERATOR):
			record_step(name, 3, skip=1)
			self.assertRaises(frappe.ValidationError, record_step, name, 3, skip=1)
			record_step(name, 4, "Pass")
			run = complete_run(name)
		doc = frappe.get_doc("Work Instruction Run", name)
		self.assertEqual((doc.status, doc.steps_done, doc.failed_steps), ("Completed", 4, 0))
		self.assertEqual(doc.completed_by, OPERATOR)
		self.assertIsNotNone(doc.duration_minutes)

	def test_recorded_results_cannot_be_edited(self):
		name = self.start()["name"]
		with as_user(OPERATOR):
			record_step(name, 1)
		doc = frappe.get_doc("Work Instruction Run", name)
		doc.steps[0].value_text = "changed"
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.steps[1].result = "Pass"  # an unrecorded step set from the form
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.steps[1].upper_limit = 99
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_cannot_complete_early(self):
		name = self.start()["name"]
		with as_user(OPERATOR):
			record_step(name, 1)
			self.assertRaises(frappe.ValidationError, complete_run, name)

	def test_failed_step_raises_a_suggestion(self):
		name = self.start()["name"]
		with as_user(OPERATOR):
			record_step(name, 1)
			run = record_step(name, 2, 39)
		self.assertEqual(run["steps"][1]["result"], "Fail")
		self.assertEqual(run["status"], "In Progress")  # step 2 does not stop the run
		sug = frappe.get_doc("Agent Suggestion", {"rule_key": f"work-instruction:{name}:step:2:fail"})
		self.assertEqual(
			(sug.category, sug.severity, sug.reference_name), ("Work Instruction", "Warning", name)
		)

	def test_stop_on_fail_holds_until_a_disposition(self):
		name = self.start()["name"]
		with as_user(OPERATOR):
			record_step(name, 1)
			record_step(name, 2, 43)
		sign_off_step(name, 2)
		with as_user(OPERATOR):
			record_step(name, 3)
			run = record_step(name, 4, "Fail")
			self.assertEqual(run["status"], "On Hold")
			self.assertIn("First part visual check", run["hold_reason"])
			self.assertRaises(frappe.ValidationError, complete_run, name)
			self.assertRaises(frappe.PermissionError, release_hold, name, "Scrap the part")
		self.assertEqual(
			frappe.db.get_value(
				"Agent Suggestion", {"rule_key": f"work-instruction:{name}:step:4:fail"}, "severity"
			),
			"Critical",
		)
		with as_user(SUPERVISOR):
			self.assertRaises(frappe.ValidationError, release_hold, name, " ")
			run = release_hold(name, "Part scrapped, die re-seated")
		self.assertEqual(run["status"], "In Progress")
		with as_user(OPERATOR):
			run = complete_run(name)
		doc = frappe.get_doc("Work Instruction Run", name)
		self.assertEqual((doc.status, doc.failed_steps, doc.disposition_by), ("Completed", 1, SUPERVISOR))

	def test_only_released_revisions_run(self):
		draft = make_instruction("T-WI-NOTYET", released=False)
		with as_user(OPERATOR):
			self.assertRaises(frappe.ValidationError, start_run, draft.name, "T-WI-PRESS")

	def test_abort_needs_a_reason_and_is_final(self):
		name = self.start()["name"]
		with as_user(OPERATOR):
			self.assertRaises(frappe.ValidationError, abort_run, name, "")
			run = abort_run(name, "Job cancelled")
			self.assertEqual(run["status"], "Aborted")
			self.assertRaises(frappe.ValidationError, record_step, name, 1)

	def test_floor_snapshot_and_stalled_rule(self):
		name = self.start()["name"]
		with as_user(OPERATOR):
			record_step(name, 1)
		snap = floor_snapshot()
		press = next(m for m in snap["machines"] if m.name == "T-WI-PRESS")
		self.assertEqual([r.name for r in press["work_instruction_runs"]], [name])
		run = next(r for r in snap["work_instruction_runs"] if r.name == name)
		self.assertEqual((run.current_step, run.current_title), (2, "Torque the die clamps"))
		self.assertEqual([r.name for r in list_active_runs("T-WI-PRESS")], [name])
		self.assertFalse([f for f in collect_findings(snap) if f["rule_key"].endswith(f"{name}:stalled")])
		frappe.db.set_value(
			"Work Instruction Run", name, "started_at", add_to_date(now_datetime(), minutes=-120)
		)
		findings = collect_findings(floor_snapshot())
		self.assertTrue([f for f in findings if f["rule_key"] == f"work-instruction:{name}:stalled"])
		self.assertEqual(get_run(name)["current_step"], 2)
