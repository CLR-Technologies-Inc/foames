# Work instructions

A work instruction is the step-by-step "how" an operator follows at a station: lock out the press, torque the die clamps to 40 to 45 Nm, check the first part, and so on. FoaMES keeps each instruction under revision control, shows it to the operator one step at a time on the Floor View, records what was done and measured at every step, and makes sure verification steps are signed off by a second person before the work goes on.

Work instructions are the execution side. The controlled document that says what must be done and why (a standard operating procedure, with its approvals, periodic review and training records) lives elsewhere; an instruction names the SOP it carries out in **Governing SOP**.

Nothing in a work instruction changes a machine. A failed check is recorded, raises an Agent Suggestion and, when the step says so, holds the run for a supervisor; what happens to the part or the machine is a person's decision.

## Writing an instruction

**Work Instruction** holds one revision of an instruction.

| Field | Meaning |
| --- | --- |
| **Instruction Code** | The same for every revision, such as `WI-PRESS-CHANGEOVER`. The record is named `<code>-REV<nn>`, for example `WI-PRESS-CHANGEOVER-REV01` |
| **Title**, **Operation** | What operators see when they pick an instruction; Operation groups them (Changeover, Setup, First-Off Inspection, Cleaning) |
| **Revision** | Set when the record is created: one more than the highest revision of the code |
| **Machine**, **Machine Type** | Where it is offered. A machine, or every machine of a machine type, or every machine when both are empty |
| **Product** | The ERP item it is for, as an External Reference; optional |
| **Governing SOP** | The code of the standard operating procedure it carries out |
| **Description**, **Safety and PPE** | Shown before the first step |
| **Steps** | The steps, in order |
| **What Changed**, **Previous Revision** | Filled by New Revision |

Each step has:

| Field | Meaning |
| --- | --- |
| **Title**, **Instruction** | What to do, as rich text |
| **Image**, **Attachment**, **Video URL** | Media shown with the step: a photo, a drawing or PDF, a video |
| **Capture** | What the operator records (below) |
| **Optional** | The operator may skip it |
| **Estimated (min)** | Adds up to the instruction's estimate, which the stalled-run rule uses |
| **Sign-off Role** | A verification point: someone else with this role signs the step off before the next step |
| **Stop on Fail** | A failed result puts the run on hold until a supervisor records a disposition |
| **Unit**, **Lower Limit**, **Target**, **Upper Limit** | For a Number step. Tick Has Lower Limit or Has Upper Limit for each limit that applies; a one-sided limit is fine |
| **Answers**, **Failing Answers** | For a Choice step, one per line |
| **Post as Measurement**, **Measurement Name** | For a Number step: also record the value as a Measurement event on the run's machine |

### Captures

| Capture | The operator | Result |
| --- | --- | --- |
| Confirm | confirms the step is done | Done |
| Pass/Fail | records a check as passed or failed | Pass or Fail |
| Number | enters a value | Pass or Fail against the limits (limits included), Done when there are none |
| Text | writes what they found: a lot number, a remark | Done |
| Choice | picks one of the answers | Fail for a failing answer, otherwise Done |

An instruction with a step that cannot work is refused: a lower limit above the upper limit, a Choice step with fewer than two answers or a failing answer that is not an answer, Post as Measurement on anything but a Number step or without a name, Stop on Fail on a step that cannot fail.

### Revisions

| Status | Meaning |
| --- | --- |
| Draft | Being written; can be edited; cannot be run |
| Released | In use on the floor; cannot be edited |
| Obsolete | Replaced or withdrawn; cannot be edited or run |

**Release** (FoaMES Engineer, FoaMES Quality or System Manager) makes a Draft the revision in use, and the revision of the same code that was in use becomes Obsolete. To change a released instruction, use **New Revision**: it copies the revision into a new Draft with the next number and asks what changes. Runs keep their own copy of the steps, so a run always shows the revision the operator actually followed.

Engineers and Quality write instructions; supervisors, operators and maintenance read them.

## Running an instruction

On the Floor View, **Work Instructions** asks for the machine and lists the released instructions that apply there: those for that machine first, then those for its machine type, then those for every machine. **Start** creates a **Work Instruction Run** and opens the runner. A run started at a machine with a current job records that job too.

The runner shows the safety notes, then one step at a time with its instruction, image, attachment and video, the limits for a reading, and a place for a note. The list on the right shows every step with what was recorded. Each machine's tile shows its active runs ("WI: Press changeover · step 2 of 4"); clicking the badge reopens the runner, and so does **Open on the Floor View** on the run's form.

- **Steps go in order.** A step cannot be recorded before the one above it.
- **Results are final.** A recorded step cannot be changed, from the runner, the form or the API. A mistake is written down in the note of a later step or by aborting and starting again.
- **Verification points.** A step with a sign-off role holds the next step until someone with that role signs it off. The person who recorded the step cannot sign it off, even if they hold the role.
- **Holds.** A failed step with Stop on Fail puts the run On Hold. A FoaMES Supervisor, Quality, Engineer or System Manager releases it with a disposition (what was decided about the part or batch), and the run continues. A run on hold cannot be completed.
- **Completing.** The run completes once every step is recorded (optional steps may be Skipped) and every sign-off is in. A failed step without Stop on Fail does not stop completion; it is counted in Failed Steps and raised as a suggestion.
- **Aborting.** A run that will not be finished is aborted with a reason. The recorded steps stay.

| Run status | Set when |
| --- | --- |
| In Progress | the run starts, or a hold is released |
| On Hold | a Stop on Fail step fails |
| Completed | every step is recorded and signed off |
| Aborted | someone stops it, with a reason |

Each step stores its result, the value, the note, who recorded it and when, and who signed it off and when. The run stores who started and ended it, its duration, its estimate, the steps done and failed, and the hold, disposition and abort details. Operators, supervisors, maintenance and quality can start and execute runs; FoaMES Engineers and System Managers can also delete them.

## Readings into SPC

A Number step with **Post as Measurement** also writes a Measurement Machine Event on the run's machine (source Manual, the measurement name from the step, keyed to the run and step so it is written once). The SPC monitor and the SPC Control Chart report treat it like any other reading of that measurement, so hand-taken checks and the machine's own sensors land on the same chart. See [spc.md](spc.md). A run without a machine records the value but posts no event.

## Suggestions

| Rule key | Category, severity | Raised when |
| --- | --- | --- |
| `work-instruction:<run>:step:<n>:fail` | Work Instruction, Warning (Critical for a Stop on Fail step) | a step is recorded as Fail, at once |
| `work-instruction:<run>:stalled` | Work Instruction, Warning | an active run has been open at least twice its estimate and at least 15 minutes over it, on the hourly suggestion run or Run suggestion rules |

The evidence names the run, instruction, machine, job, step, value, limits, the person who recorded it and their note. The stalled suggestion is marked Done when the run completes or is aborted; failed-step suggestions stay for quality to review. The rules are pure logic in `foames/foames_mes/work_instructions.py`.

## In the floor snapshot

Each machine has `work_instruction_runs` (its active runs) and the snapshot has `work_instruction_runs` (all of them, oldest first), each with `name`, `work_instruction`, `title`, `machine`, `job_reference`, `status`, `started_at`, `started_by`, `minutes_open`, `estimated_minutes`, `steps_done`, `steps_total`, `failed_steps`, `current_step`, `current_title` and `hold_reason`.

## From a tablet app, a SCADA screen or an agent

| Method | Verb | Arguments | Returns |
| --- | --- | --- | --- |
| `foames.foames_mes.doctype.work_instruction.work_instruction.list_instructions_for_machine` | GET | `machine` | Released instructions that apply there, with `scope` |
| `foames.foames_mes.doctype.work_instruction_run.work_instruction_run.start_run` | POST | `work_instruction`, `machine`, `job_reference` | The run |
| `...work_instruction_run.get_run` | GET | `name` | The run with every step, `current_step`, `progress` and `completion_gaps` |
| `...work_instruction_run.record_step` | POST | `name`, `step_no`, `value`, `note`, `skip` | The run |
| `...work_instruction_run.sign_off_step` | POST | `name`, `step_no` | The run |
| `...work_instruction_run.release_hold` | POST | `name`, `disposition` | The run |
| `...work_instruction_run.complete_run` | POST | `name` | The run |
| `...work_instruction_run.abort_run` | POST | `name`, `reason` | The run |
| `...work_instruction_run.list_active_runs` | GET | `machine` | Active runs with the step each is on |
| `foames.foames_mes.doctype.work_instruction.work_instruction.release` / `make_obsolete` / `new_revision` | POST | `name` (`change_note` for a new revision) | The revision's name and status |

`value` is the reading for a Number step, `Pass` or `Fail` for a check, the text or the answer for Text and Choice steps, and is ignored for Confirm. Errors (a step out of order, a value outside what the step takes, a sign-off by the person who did the step) come back as validation errors with the reason.
