# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One execution of a released work instruction at a machine, step by step.

The run copies the revision's steps when it starts, so it stays a complete record of what the
operator was told and what they recorded, whatever happens to the instruction later. Steps are
recorded in order through `record_step`, verification points are signed off by a second person
through `sign_off_step`, a failed Stop on Fail step puts the run On Hold until `release_hold`, and
the run ends with `complete_run` or `abort_run`. Recorded results cannot be changed afterwards,
from the API or the form.

A failed step raises an Agent Suggestion at once. A Number step marked Post as Measurement also
writes a Measurement Machine Event on the run's machine (source Manual), so SPC charts hand-taken
readings next to the machine's own. The pure rules are in foames.foames_mes.work_instructions.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, now_datetime

from foames.foames_mes.counters import minutes_between
from foames.foames_mes.work_instructions import (
	RUN_ACTIVE,
	RUN_FINAL,
	StepError,
	allowed_run_transition,
	can_record,
	can_sign_off,
	completion_gaps,
	current_step,
	evaluate_capture,
	failed_step_finding,
	progress,
)

# Copied from each template step into the run.
FROZEN_FIELDS = (
	"title",
	"capture",
	"optional",
	"estimated_minutes",
	"sign_off_role",
	"stop_on_fail",
	"instruction",
	"image",
	"attachment",
	"video_url",
	"unit",
	"has_lower_limit",
	"lower_limit",
	"target_value",
	"has_upper_limit",
	"upper_limit",
	"choices",
	"failing_choices",
	"post_measurement",
	"measurement_name",
)
# Set once when a step is recorded or signed off; never changed afterwards.
RESULT_FIELDS = (
	"result",
	"value_text",
	"value_number",
	"note",
	"completed_at",
	"completed_by",
	"signed_off_at",
	"signed_off_by",
	"machine_event",
)


class WorkInstructionRun(Document):
	def before_insert(self):
		instruction = frappe.get_doc("Work Instruction", self.work_instruction)
		if instruction.status != "Released":
			frappe.throw(
				_("Work Instruction {0} is {1}; only a released revision can be run").format(
					instruction.name, _(instruction.status)
				)
			)
		if instruction.machine and self.machine and instruction.machine != self.machine:
			frappe.throw(
				_("Work Instruction {0} is for machine {1}, not {2}").format(
					instruction.name, instruction.machine, self.machine
				)
			)
		self.machine = self.machine or instruction.machine
		self.instruction_code, self.revision = instruction.instruction_code, instruction.revision
		self.title = instruction.title
		self.estimated_minutes = instruction.estimated_minutes
		if self.machine and not self.job_reference:
			self.job_reference = frappe.db.get_value("Machine", self.machine, "current_job_reference")
		self.status = "In Progress"
		self.started_at, self.started_by = now_datetime(), frappe.session.user
		self.set("steps", [])
		for step in instruction.steps:
			self.append("steps", {"step_no": step.idx, **{f: step.get(f) for f in FROZEN_FIELDS}})

	def validate(self):
		before = None if self.is_new() else self.get_doc_before_save()
		previous = before.status if before else None
		if not allowed_run_transition(previous, self.status):
			frappe.throw(
				_("A Work Instruction Run cannot go from {0} to {1}").format(_(previous), _(self.status))
			)
		if before:
			self._guard_frozen(before)
		if self.status == "Completed":
			gaps = completion_gaps(self.step_dicts())
			if gaps:
				frappe.throw("<br>".join(frappe.utils.escape_html(g) for g in gaps), title=_("Not finished"))
		if self.status in RUN_FINAL and not self.completed_at:
			self.completed_at, self.completed_by = now_datetime(), frappe.session.user
		state = progress(self.step_dicts())
		self.steps_done, self.steps_total, self.failed_steps = state["done"], state["total"], state["failed"]
		end = get_datetime(self.completed_at) if self.completed_at else None
		self.duration_minutes = minutes_between(get_datetime(self.started_at), end) if end else None

	def on_update(self):
		if self.status in RUN_FINAL:
			_close_suggestion(f"work-instruction:{self.name}:stalled", self.status)

	def _guard_frozen(self, before):
		previous = {row.name: row for row in before.steps}
		if len(previous) != len(self.steps) or any(row.name not in previous for row in self.steps):
			frappe.throw(_("The steps of a run cannot be added or removed"))
		for row in self.steps:
			old = previous[row.name]
			for field in ("step_no", *FROZEN_FIELDS):
				if row.get(field) != old.get(field):
					frappe.throw(
						_("Step {0} is copied from the instruction and cannot be edited").format(row.idx)
					)
			for field in RESULT_FIELDS:
				if old.get(field) not in (None, "", 0) and row.get(field) != old.get(field):
					frappe.throw(_("Step {0} is already recorded and cannot be changed").format(row.idx))
			if not self.flags.recording and any(row.get(field) != old.get(field) for field in RESULT_FIELDS):
				frappe.throw(_("Record steps from the Floor View or the API, not by editing the run"))

	def step_dicts(self) -> list[dict]:
		return [{**row.as_dict(), "idx": row.step_no or row.idx} for row in self.steps]

	def step(self, step_no: int):
		for row in self.steps:
			if (row.step_no or row.idx) == step_no:
				return row
		frappe.throw(_("There is no step {0}").format(step_no))

	def save_recording(self):
		self.flags.recording = True
		try:
			self.save()
		finally:
			self.flags.recording = False


def _close_suggestion(rule_key: str, status: str):
	name = frappe.db.get_value("Agent Suggestion", {"rule_key": rule_key, "status": "Open"}, "name")
	if name:
		doc = frappe.get_doc("Agent Suggestion", name)
		doc.status = "Done"
		doc.resolution = _("The run is {0}").format(_(status))
		doc.save(ignore_permissions=True)


def _run_for_update(name: str) -> WorkInstructionRun:
	doc = frappe.get_doc("Work Instruction Run", name)
	doc.check_permission("write")
	return doc


def _throw_step_error(error: StepError):
	frappe.throw(str(error), title=_("Step not recorded"))


def run_payload(doc: WorkInstructionRun) -> dict:
	"""The run as the Floor View runner and agents read it."""
	steps = doc.step_dicts()
	current = current_step(steps)
	instruction = (
		frappe.db.get_value(
			"Work Instruction", doc.work_instruction, ["description", "safety_notes"], as_dict=True
		)
		or {}
	)
	return {
		"name": doc.name,
		"work_instruction": doc.work_instruction,
		"title": doc.title,
		"revision": doc.revision,
		"machine": doc.machine,
		"job_reference": doc.job_reference,
		"status": doc.status,
		"started_at": doc.started_at,
		"started_by": doc.started_by,
		"hold_reason": doc.hold_reason,
		"description": instruction.get("description"),
		"safety_notes": instruction.get("safety_notes"),
		"estimated_minutes": doc.estimated_minutes,
		"current_step": current["idx"] if current else None,
		"progress": progress(steps),
		"completion_gaps": completion_gaps(steps),
		"steps": [
			{
				"step_no": s["idx"],
				**{f: s.get(f) for f in FROZEN_FIELDS},
				**{f: s.get(f) for f in RESULT_FIELDS},
			}
			for s in steps
		],
	}


@frappe.whitelist(methods=["POST"])
def start_run(work_instruction: str, machine: str | None = None, job_reference: str | None = None) -> dict:
	"""Start a run of a released work instruction, at a machine when given."""
	frappe.has_permission("Work Instruction Run", "create", throw=True)
	doc = frappe.get_doc(
		{
			"doctype": "Work Instruction Run",
			"work_instruction": work_instruction,
			"machine": machine or None,
			"job_reference": job_reference or None,
		}
	).insert()
	return run_payload(doc)


@frappe.whitelist()
def get_run(name: str) -> dict:
	doc = frappe.get_doc("Work Instruction Run", name)
	doc.check_permission("read")
	return run_payload(doc)


@frappe.whitelist(methods=["POST"])
def record_step(
	name: str,
	step_no: int,
	value: str | int | float | None = None,
	note: str | None = None,
	skip: bool = False,
) -> dict:
	"""Record the result of a step: the operator's confirmation, check, value, text or answer.

	Steps go in order, and a step waiting for its sign-off holds the ones after it. `skip` records an
	optional step as Skipped. Returns the run as `get_run` does."""
	doc = _run_for_update(name)
	if doc.status != "In Progress":
		frappe.throw(_("Run {0} is {1}").format(doc.name, _(doc.status)))
	step_no, skip = cint(step_no), bool(cint(skip))
	try:
		can_record(doc.step_dicts(), step_no, skip=skip)
		row = doc.step(step_no)
		outcome = (
			{"result": "Skipped", "value_number": None, "value_text": None}
			if skip
			else evaluate_capture(row.as_dict(), value)
		)
	except StepError as error:
		_throw_step_error(error)
	row.result = outcome["result"]
	row.value_text = outcome["value_text"]
	row.value_number = outcome["value_number"]
	row.note = note or None
	row.completed_at, row.completed_by = now_datetime(), frappe.session.user
	if row.result == "Fail" and row.stop_on_fail:
		doc.status = "On Hold"
		doc.hold_reason = _("Step {0} ({1}) failed with {2}").format(step_no, row.title, row.value_text)
	if row.post_measurement and row.value_number is not None and doc.machine:
		row.machine_event = _post_measurement(doc, row)
	doc.save_recording()
	if row.result == "Fail":
		from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

		run = {
			"name": doc.name,
			"work_instruction": doc.work_instruction,
			"machine": doc.machine,
			"job_reference": doc.job_reference,
		}
		raise_suggestions([failed_step_finding(run, {**row.as_dict(), "idx": step_no})])
	return run_payload(doc)


def _post_measurement(doc: WorkInstructionRun, row) -> str:
	"""A Measurement event on the run's machine for a hand-taken reading, keyed so it is written once."""
	event = frappe.get_doc(
		{
			"doctype": "Machine Event",
			"machine": doc.machine,
			"event_type": "Measurement",
			"timestamp": row.completed_at,
			"source": "Manual",
			"measurement_name": row.measurement_name.strip(),
			"value": row.value_number,
			"text": f"{doc.name} step {row.step_no or row.idx}",
			"event_key": f"work-instruction:{doc.name}:{row.step_no or row.idx}",
		}
	).insert(ignore_permissions=True)
	return event.name


@frappe.whitelist(methods=["POST"])
def sign_off_step(name: str, step_no: int) -> dict:
	"""Sign a verification step off. The signer needs the step's sign-off role and must not be the
	person who recorded it."""
	doc = _run_for_update(name)
	if doc.status not in RUN_ACTIVE:
		frappe.throw(_("Run {0} is {1}").format(doc.name, _(doc.status)))
	row = doc.step(cint(step_no))
	try:
		can_sign_off(
			{**row.as_dict(), "idx": row.step_no or row.idx}, frappe.session.user, frappe.get_roles()
		)
	except StepError as error:
		_throw_step_error(error)
	row.signed_off_at, row.signed_off_by = now_datetime(), frappe.session.user
	doc.save_recording()
	return run_payload(doc)


HOLD_ROLES = ("FoaMES Supervisor", "FoaMES Quality", "FoaMES Engineer", "System Manager")


@frappe.whitelist(methods=["POST"])
def release_hold(name: str, disposition: str) -> dict:
	"""A supervisor, quality or an engineer records what was decided about a failed hold step, and
	the run continues."""
	doc = _run_for_update(name)
	if not set(frappe.get_roles()) & set(HOLD_ROLES):
		frappe.throw(_("Only {0} can release a hold").format(", ".join(HOLD_ROLES)), frappe.PermissionError)
	if doc.status != "On Hold":
		frappe.throw(_("Run {0} is not on hold").format(doc.name))
	if not (disposition or "").strip():
		frappe.throw(_("Record the disposition: what was decided about the failed step"))
	doc.status = "In Progress"
	doc.disposition = disposition.strip()
	doc.disposition_by = frappe.session.user
	doc.save()
	return run_payload(doc)


@frappe.whitelist(methods=["POST"])
def complete_run(name: str) -> dict:
	"""End the run once every required step is recorded and every sign-off is in."""
	doc = _run_for_update(name)
	if doc.status != "Completed":
		doc.status = "Completed"
		doc.save()
	return run_payload(doc)


@frappe.whitelist(methods=["POST"])
def abort_run(name: str, reason: str) -> dict:
	"""Stop a run that will not be finished, with the reason. The recorded steps stay."""
	doc = _run_for_update(name)
	if not (reason or "").strip():
		frappe.throw(_("Say why the run is aborted"))
	if doc.status != "Aborted":
		doc.status = "Aborted"
		doc.abort_reason = reason.strip()
		doc.save()
	return run_payload(doc)


def active_runs(now=None, machine: str | None = None) -> list[dict]:
	"""In-progress and on-hold runs with minutes open and their progress, oldest first, for the floor
	snapshot and the stalled-run rule."""
	now = now or now_datetime()
	filters = {"status": ("in", list(RUN_ACTIVE))}
	if machine:
		filters["machine"] = machine
	runs = frappe.get_all(
		"Work Instruction Run",
		filters=filters,
		fields=[
			"name",
			"work_instruction",
			"title",
			"machine",
			"job_reference",
			"status",
			"started_at",
			"started_by",
			"estimated_minutes",
			"steps_done",
			"steps_total",
			"failed_steps",
			"hold_reason",
		],
		order_by="started_at asc",
	)
	if not runs:
		return runs
	step = frappe.qb.DocType("Work Instruction Run Step")
	rows = (
		frappe.qb.from_(step)
		.select(
			step.parent,
			step.step_no,
			step.idx,
			step.title,
			step.result,
			step.sign_off_role,
			step.signed_off_by,
		)
		.where(step.parent.isin([r.name for r in runs]) & (step.parenttype == "Work Instruction Run"))
		.orderby(step.parent)
		.orderby(step.idx)
		.run(as_dict=True)
	)
	by_run: dict[str, list[dict]] = {}
	for r in rows:
		by_run.setdefault(r.parent, []).append({**r, "idx": r.step_no or r.idx})
	for run in runs:
		current = current_step(by_run.get(run.name, []))
		run["current_step"] = current["idx"] if current else None
		run["current_title"] = current["title"] if current else None
		run["minutes_open"] = minutes_between(get_datetime(run.started_at), now)
	return runs


@frappe.whitelist()
def list_active_runs(machine: str | None = None) -> list[dict]:
	"""In-progress and on-hold runs, oldest first, with the step each one is on."""
	frappe.has_permission("Work Instruction Run", "read", throw=True)
	return active_runs(machine=machine)
