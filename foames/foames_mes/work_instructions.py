# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Work instructions as pure logic: step captures, step order, sign-offs and the rules. No Frappe
dependency.

A Work Instruction is the step-by-step "how" an operator follows at a station: one record per
revision, edited as a Draft, Released for use, and made Obsolete when a later revision is released.
A Work Instruction Run is one execution of a released revision at a machine. Each step of the run
is a frozen copy of the template step, so the run stays readable after the instruction changes, and
each step records what the operator did or measured:

- Confirm: the operator confirms the step is done.
- Pass/Fail: the operator records a check as passed or failed.
- Number: the operator enters a value; with limits it passes or fails against them.
- Text: the operator writes what they found (a lot number, a remark).
- Choice: the operator picks one of the listed answers; answers listed as failing fail the step.

Steps are done in order. A step with a sign-off role is a verification point: the next step waits
until a second person with that role, not the one who did the step, signs it off. A failed step
with Stop on Fail puts the run On Hold until a supervisor records a disposition. A run completes
only when every required step has a result and every sign-off is in.

FoaMES never changes a machine because of a work instruction. A failed step becomes an Agent
Suggestion for quality to review, and a run that takes far longer than the instruction's estimate
becomes one for the supervisor.
"""

from __future__ import annotations

CAPTURES = ("Confirm", "Pass/Fail", "Number", "Text", "Choice")
RESULTS_COMPLETE = ("Done", "Pass", "Fail", "Skipped")

TEMPLATE_STATUSES = ("Draft", "Released", "Obsolete")
RUN_STATUSES = ("In Progress", "On Hold", "Completed", "Aborted")
RUN_ACTIVE = ("In Progress", "On Hold")
RUN_FINAL = ("Completed", "Aborted")

# A run open longer than this multiple of its estimate (and at least STALLED_MIN_MINUTES over it)
# is reported as stalled.
STALLED_FACTOR = 2.0
STALLED_MIN_MINUTES = 15.0


class StepError(ValueError):
	"""A value that the step cannot accept, or a step that cannot be recorded yet."""


# Status flows


def allowed_template_transition(previous: str | None, new: str) -> bool:
	"""Draft -> Released -> Obsolete, and Draft -> Obsolete for a revision that is never used.
	Released and Obsolete revisions never go back to Draft: a change is a new revision."""
	if previous is None or previous == new:
		return new in TEMPLATE_STATUSES
	return (previous, new) in {("Draft", "Released"), ("Draft", "Obsolete"), ("Released", "Obsolete")}


def allowed_run_transition(previous: str | None, new: str) -> bool:
	"""In Progress <-> On Hold, and either of them to Completed or Aborted. Completed and Aborted
	are final. A run on hold must be released before it can complete."""
	if previous is None:
		return new == "In Progress"
	if previous == new:
		return True
	if previous in RUN_FINAL:
		return False
	if previous == "On Hold" and new == "Completed":
		return False
	return new in RUN_STATUSES


# Capture


def parse_choices(text: str | None) -> list[str]:
	"""One answer per line (or comma separated on one line), blanks dropped, order kept."""
	if not text:
		return []
	lines = [line.strip() for line in str(text).splitlines()]
	if len([line for line in lines if line]) == 1 and "," in lines[0]:
		lines = [part.strip() for part in lines[0].split(",")]
	seen, out = set(), []
	for line in lines:
		if line and line not in seen:
			seen.add(line)
			out.append(line)
	return out


def limits_of(step: dict) -> tuple[float | None, float | None]:
	"""(lower, upper) of a Number step; None for a side without a limit."""
	lower = step.get("lower_limit") if step.get("has_lower_limit") else None
	upper = step.get("upper_limit") if step.get("has_upper_limit") else None
	return (
		float(lower) if lower is not None else None,
		float(upper) if upper is not None else None,
	)


def validate_template_step(step: dict) -> list[str]:
	"""Problems with a step definition, as messages; empty when the step is usable."""
	problems = []
	title = step.get("title") or f"step {step.get('idx') or '?'}"
	capture = step.get("capture") or "Confirm"
	if capture not in CAPTURES:
		problems.append(f"{title}: unknown capture {capture}")
	if capture == "Number":
		lower, upper = limits_of(step)
		if lower is not None and upper is not None and lower > upper:
			problems.append(f"{title}: the lower limit {lower:g} is above the upper limit {upper:g}")
	if capture == "Choice":
		choices = parse_choices(step.get("choices"))
		if len(choices) < 2:
			problems.append(f"{title}: a Choice step needs at least two answers")
		failing = parse_choices(step.get("failing_choices"))
		unknown = [c for c in failing if c not in choices]
		if unknown:
			problems.append(f"{title}: failing answers not among the answers: {', '.join(unknown)}")
	if step.get("post_measurement"):
		if capture != "Number":
			problems.append(f"{title}: only a Number step can post a measurement")
		elif not (step.get("measurement_name") or "").strip():
			problems.append(f"{title}: a step that posts a measurement needs a measurement name")
	if step.get("stop_on_fail") and capture not in ("Pass/Fail", "Number", "Choice"):
		problems.append(f"{title}: Stop on Fail needs a step that can fail (Pass/Fail, Number or Choice)")
	return problems


def evaluate_capture(step: dict, value=None) -> dict:
	"""What recording `value` against `step` gives: {result, value_number, value_text}.

	Raises StepError for a value the step cannot take. A Number step with limits passes when the
	value is inside them (limits included) and fails otherwise; without limits it is Done."""
	capture = step.get("capture") or "Confirm"
	text = None if value is None else str(value).strip()
	if capture == "Confirm":
		return {"result": "Done", "value_number": None, "value_text": text or None}
	if capture == "Pass/Fail":
		answer = (text or "").lower()
		if answer in ("pass", "passed", "ok", "1", "true", "yes"):
			return {"result": "Pass", "value_number": None, "value_text": "Pass"}
		if answer in ("fail", "failed", "nok", "0", "false", "no"):
			return {"result": "Fail", "value_number": None, "value_text": "Fail"}
		raise StepError("Record Pass or Fail")
	if capture == "Number":
		if text in (None, ""):
			raise StepError("Enter a number")
		try:
			number = float(text)
		except (TypeError, ValueError):
			raise StepError(f"{value!r} is not a number") from None
		if number != number or number in (float("inf"), float("-inf")):
			raise StepError(f"{value!r} is not a number")
		lower, upper = limits_of(step)
		if lower is None and upper is None:
			result = "Done"
		elif (lower is not None and number < lower) or (upper is not None and number > upper):
			result = "Fail"
		else:
			result = "Pass"
		return {"result": result, "value_number": number, "value_text": text}
	if capture == "Text":
		if not text:
			raise StepError("Write what you found")
		return {"result": "Done", "value_number": None, "value_text": text}
	if capture == "Choice":
		choices = parse_choices(step.get("choices"))
		if text not in choices:
			raise StepError(f"Pick one of: {', '.join(choices)}")
		failing = parse_choices(step.get("failing_choices"))
		return {"result": "Fail" if text in failing else "Done", "value_number": None, "value_text": text}
	raise StepError(f"Unknown capture {capture}")


# Order and completion


def is_complete(step: dict) -> bool:
	return step.get("result") in RESULTS_COMPLETE


def awaiting_sign_off(step: dict) -> bool:
	return (
		bool(step.get("sign_off_role"))
		and is_complete(step)
		and step.get("result") != "Skipped"
		and not step.get("signed_off_by")
	)


def current_step(steps: list[dict]) -> dict | None:
	"""The step the operator is on: the first one not yet recorded, or the first one waiting for its
	sign-off, whichever comes first. None when every step is recorded and signed off."""
	for step in steps:
		if not is_complete(step) or awaiting_sign_off(step):
			return step
	return None


def can_record(steps: list[dict], step_no: int, skip: bool = False) -> None:
	"""Raise StepError unless the step `step_no` (its idx) may be recorded now."""
	target = next((s for s in steps if s.get("idx") == step_no), None)
	if target is None:
		raise StepError(f"There is no step {step_no}")
	if is_complete(target):
		raise StepError(f"Step {step_no} is already recorded")
	if skip and not target.get("optional"):
		raise StepError(f"Step {step_no} is required and cannot be skipped")
	for step in steps:
		if step.get("idx") >= step_no:
			break
		if not is_complete(step):
			raise StepError(f"Step {step['idx']} ({step.get('title')}) comes first")
		if awaiting_sign_off(step):
			raise StepError(
				f"Step {step['idx']} ({step.get('title')}) is waiting for a sign-off by {step.get('sign_off_role')}"
			)


def can_sign_off(step: dict, user: str, user_roles) -> None:
	"""Raise StepError unless `user` may sign this step off: it is recorded, has a sign-off role the
	user holds, is not yet signed off, and was recorded by someone else (two-person rule)."""
	if not step.get("sign_off_role"):
		raise StepError(f"Step {step.get('idx')} needs no sign-off")
	if not is_complete(step) or step.get("result") == "Skipped":
		raise StepError(f"Step {step.get('idx')} has not been recorded yet")
	if step.get("signed_off_by"):
		raise StepError(f"Step {step.get('idx')} is already signed off")
	if step.get("sign_off_role") not in set(user_roles or ()):
		raise StepError(f"Step {step.get('idx')} must be signed off by {step.get('sign_off_role')}")
	if step.get("completed_by") == user:
		raise StepError(
			f"Step {step.get('idx')} must be signed off by someone other than the person who did it"
		)


def completion_gaps(steps: list[dict]) -> list[str]:
	"""Why a run cannot be completed yet, one message per step; empty when it can."""
	gaps = []
	for step in steps:
		label = f"Step {step.get('idx')} ({step.get('title')})"
		if not is_complete(step):
			gaps.append(f"{label} is not recorded")
		elif awaiting_sign_off(step):
			gaps.append(f"{label} is waiting for a sign-off by {step.get('sign_off_role')}")
	return gaps


def progress(steps: list[dict]) -> dict:
	"""{done, total, failed, current_idx, current_title} for a run's steps."""
	current = current_step(steps)
	return {
		"done": sum(1 for s in steps if is_complete(s) and not awaiting_sign_off(s)),
		"total": len(steps),
		"failed": sum(1 for s in steps if s.get("result") == "Fail"),
		"current_idx": current.get("idx") if current else None,
		"current_title": current.get("title") if current else None,
	}


def estimated_minutes(steps: list[dict]) -> float:
	return float(sum(float(s.get("estimated_minutes") or 0) for s in steps))


# Rules


def failed_step_finding(run: dict, step: dict) -> dict:
	"""The suggestion for a failed step, raised as soon as it is recorded."""
	where = run.get("machine") or "no machine"
	limits = limits_of(step)
	return {
		"rule_key": f"work-instruction:{run['name']}:step:{step['idx']}:fail",
		"category": "Work Instruction",
		"severity": "Critical" if step.get("stop_on_fail") else "Warning",
		"title": f"Failed step {step['idx']} of {run.get('work_instruction')} at {where}",
		"suggestion": (
			f"Step {step['idx']} ({step.get('title')}) of work instruction {run.get('work_instruction')} "
			f"failed at {where} with {step.get('value_text') or step.get('result')}. "
			+ (
				"The run is on hold until a supervisor records a disposition. "
				if step.get("stop_on_fail")
				else ""
			)
			+ "Review the part or batch and decide whether it needs rework, a quality hold or a change to the instruction."
		),
		"reference_doctype": "Work Instruction Run",
		"reference_name": run["name"],
		"evidence": {
			"run": run["name"],
			"work_instruction": run.get("work_instruction"),
			"machine": run.get("machine"),
			"job_reference": run.get("job_reference"),
			"step": step["idx"],
			"step_title": step.get("title"),
			"capture": step.get("capture"),
			"value": step.get("value_text"),
			"lower_limit": limits[0],
			"upper_limit": limits[1],
			"unit": step.get("unit"),
			"completed_by": step.get("completed_by"),
			"note": step.get("note"),
		},
	}


def stalled_runs(snapshot: dict) -> list[dict]:
	"""Suggestions for active runs open far longer than their instruction's estimate.

	Reads `snapshot["work_instruction_runs"]`: dicts with name, work_instruction, machine, status,
	minutes_open, estimated_minutes, steps_done, steps_total and current_title."""
	out = []
	for run in snapshot.get("work_instruction_runs", []):
		if run.get("status") not in RUN_ACTIVE:
			continue
		estimate = float(run.get("estimated_minutes") or 0)
		minutes = float(run.get("minutes_open") or 0)
		if estimate <= 0:
			continue
		if minutes < estimate * STALLED_FACTOR or minutes - estimate < STALLED_MIN_MINUTES:
			continue
		where = run.get("machine") or "no machine"
		out.append(
			{
				"rule_key": f"work-instruction:{run['name']}:stalled",
				"category": "Work Instruction",
				"severity": "Warning",
				"title": f"{run.get('work_instruction')} at {where} open {minutes:.0f} min, estimate {estimate:.0f}",
				"suggestion": (
					f"Work instruction run {run['name']} ({run.get('work_instruction')}) at {where} has been "
					f"{str(run.get('status')).lower()} for {minutes:.0f} minutes against an estimate of {estimate:.0f}. "
					f"It is at step {run.get('steps_done', 0) + 1} of {run.get('steps_total', 0)}"
					+ (f" ({run.get('current_title')})" if run.get("current_title") else "")
					+ ". Check whether the operator needs help, or abort the run if it was abandoned."
				),
				"reference_doctype": "Work Instruction Run",
				"reference_name": run["name"],
				"evidence": {
					"run": run["name"],
					"status": run.get("status"),
					"minutes_open": round(minutes, 1),
					"estimated_minutes": estimate,
					"steps_done": run.get("steps_done"),
					"steps_total": run.get("steps_total"),
					"current_step": run.get("current_title"),
				},
			}
		)
	return out
