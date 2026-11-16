# Process validation and equipment qualification

FoaMES records the qualification of equipment and the validation of processes the way regulated and
quality-managed plants already do it: an approved protocol states what will be tested and what counts
as passing; an execution records what was observed, with evidence and deviations; someone other than
the person who ran it approves it; and the qualification lapses after a set period so it is done
again. Criteria on machine measurements are judged from the same Measurement events the
[SPC charts](spc.md) use, so capability and statistical control come from the data the machine sent,
not from a number typed in afterwards.

This is known practice, laid out in public guidance:

- US FDA, *Process Validation: General Principles and Practices* (2011): the three-stage life cycle.
- GHTF SG3/N99-10, *Quality Management Systems: Process Validation Guidance* (2004): IQ, OQ and PQ.
- EU GMP Annex 15, *Qualification and Validation* (2015).
- AIAG *Statistical Process Control* manual for the capability indices.

FoaMES gives you the records and the rules between them. It does not by itself make a system
compliant with 21 CFR Part 11 or EU GMP Annex 11: your quality system decides how the site is
validated, how users authenticate and how electronic records are retained.

## The life cycle

| Stage | Protocol types | What it shows |
| --- | --- | --- |
| 1. Process design | (before FoaMES) | The process and its critical parameters are understood |
| 2. Process qualification | **IQ** installation, **OQ** operational, **PQ** performance qualification of a machine; **PPQ** process performance qualification | The equipment is installed and works across its range; the process, run at commercial scale, consistently meets its specifications |
| 3. Continued process verification | **CPV** | The process stays in a state of control in routine production |

The types follow one another. An execution of OQ cannot be approved until the machine's IQ is
current, PQ needs a current OQ, a PPQ that names a machine needs that machine's PQ, and CPV needs the
process's PPQ. Clear **Enforce Sequence** on a protocol to drop the check (for example for equipment
qualified before FoaMES was installed; record why in the protocol's scope).

## Setting up a protocol

Create a **Validation Protocol** (FoaMES Quality workspace, Validation card):

| Field | Meaning |
| --- | --- |
| Protocol Type | IQ, OQ, PQ, PPQ or CPV; the validation stage is filled in |
| Machine | Required for IQ, OQ and PQ. On a PPQ it names the equipment whose PQ must be current |
| Process | Required for PPQ and CPV: the process being validated, by name |
| Consecutive Passing Runs | How many executions in a row must pass before the subject counts as qualified; 3 for PPQ and 1 otherwise unless you set it |
| Validity (Months) | Requalify after this many months (default 12); 0 means it does not lapse |
| Objective, Scope, Procedure | The protocol text |
| Acceptance Criteria | One row per criterion (below) |

Submitting the protocol approves it and records who approved it and when. An approved protocol is
changed by cancelling and amending it, so every execution keeps pointing at the text it was run
against.

### Acceptance criteria

| Check | Judged from | Passes when |
| --- | --- | --- |
| Pass/Fail | A person answers Check Met: Yes or No | Yes |
| Numeric Range, source Manual | The Recorded Value entered during the test | The value lies within the limits (a value on a limit is inside) |
| Numeric Range, source Machine Data | Every reading of the measurement in the execution window | Every reading lies within the limits; the worst one is shown |
| Capability | The readings of the measurement in the window | The chosen index (Cpk or Ppk) reaches the minimum (default 1.33), from at least Minimum Readings (default 25), and no reading is out of specification |
| Statistical Control | The readings of the measurement in the window | No run-rule signal (Nelson or Western Electric) on the I-MR chart, from at least Minimum Readings |

**Limits** says which sides are real: Lower and Upper, Lower Only or Upper Only. **Measurement** is
the `measurement_name` of Measurement-type Machine Events, read from the protocol's machine unless the
row names another. **Critical** marks a criterion whose failure fails the execution outright.
**Evidence Required** means the result needs an attached file (a calibration certificate, a photo,
a printout) or machine-data evidence before it can be approved.

### Capability indices

For readings x with mean x̄ and specification limits LSL and USL:

| Index | Formula | Sigma |
| --- | --- | --- |
| Cp | (USL − LSL) / 6σ | within: MR̄ / d2 of the readings in time order |
| Cpk | min(USL − x̄, x̄ − LSL) / 3σ | within |
| Pp | (USL − LSL) / 6s | overall: the sample standard deviation |
| Ppk | min(USL − x̄, x̄ − LSL) / 3s | overall |

With one limit, Cpk and Ppk use that side and Cp and Pp are not defined. Cpk shows what the process
can do when only common-cause variation is present; Ppk shows what it did over the whole run, so it
is the stricter choice for a PPQ. `foames.foames_mes.spc.capability` computes them and has no Frappe
dependency.

## From commissioning

Qualification starts where [commissioning](commissioning.md) ends. When a Commissioning Package is
handed over, `foames.foames_validation.commissioning.on_handover` (registered on the
`foames_commissioning_handed_over` hook) does this for each machine in the package's scope:

- If the machine has an approved IQ protocol, it opens a draft Validation Execution of the latest
  one, with **Commissioning Package** set, so the IQ can reference the package's handover dossier
  (`get_handover_dossier`). A draft of that protocol that is already open is reused.
- If it has none, it raises an Agent Suggestion (Quality, rule key
  `validation:iq-after-handover:<machine>`) to write and approve one. FoaMES does not write a
  protocol on its own.

The first execution opened is written back to the package's **Qualification Type** and
**Qualification Record**.

## Executing a protocol

Create a **Validation Execution** for an approved protocol (or use **New Execution** on the protocol).
The protocol's criteria are copied into the Results table, so a later amendment does not change what
this run was judged against. The run number counts the protocol's executions.

1. Set **Started On** when the test starts and **Ended On** when it ends. Machine-data criteria read
   the Measurement events between the two.
2. Record the manual results: Check Met for Pass/Fail rows, Recorded Value for manual ranges. The
   result, summary and observed value are filled in on save.
3. Press **Evaluate Machine Data** to judge the machine-data rows now. Each row gets its result, the
   number of readings, a summary and its evidence as JSON (the index or signals, mean, sigmas,
   limits, the window and the first and last reading).
4. Attach evidence where it is required, and mark a row **Not Applicable** if it does not apply,
   giving the reason in its deviation.
5. For each failed row, write up the **Deviation** (what differed, the investigation, its reference
   in your deviation system), an **Impact Assessment**, and a **Disposition**: *Accepted: no impact
   on the conclusion* or *Rejected: the criterion is not met*.

**Open Items** lists what still stops approval. The status moves from Draft (not started) to In
Progress to Ready for Review.

### Approval

Submitting the execution approves it. Approval:

- is refused to the person in **Executed By**: the reviewer must be someone else;
- evaluates the machine-data criteria again, so the stored evidence is what the approval rests on;
- needs every result in, a deviation and disposition for every failure, evidence where required;
- needs the prerequisite qualification to be current (unless the protocol's sequence is not
  enforced or the execution failed);
- sets the outcome: **Passed**; **Passed with Deviations** when every failure is non-critical and
  accepted; **Failed** when a critical criterion failed or a deviation was rejected;
- sets **Qualified Until** to the approval date plus the protocol's validity, less one day.

Operators, supervisors and maintenance can create and fill in executions; approving them needs the
FoaMES Quality or FoaMES Engineer role (or System Manager). Protocols and executions keep a version
history (track changes).

## Qualification status

For each machine (IQ, OQ, PQ) and process (PPQ, CPV) with an approved protocol, the latest approved
execution decides:

| Status | When |
| --- | --- |
| Qualified | It passed, its consecutive runs are complete and it has not lapsed |
| Due Soon | It lapses within 30 days |
| Expired | Its Qualified Until date has passed |
| Runs Pending | It passed, but fewer consecutive runs of the protocol than required have passed |
| Not Qualified | No approved execution yet, or the latest one failed |

A cancelled execution no longer counts. The **Qualification Status** script report (FoaMES Quality
workspace) lists every subject with filters for machine, process, type and status.
`foames.foames_validation.api.get_qualification_status(machine, process, protocol_type)` returns the
same rows as JSON, and the MCP tool `foames_get_qualification_status` exposes it to agents.

## Requalification suggestions

Once a day `foames.foames_validation.tasks.check_requalification` raises an Agent Suggestion
(category Quality) for every qualification that is Due Soon (Warning) or Expired (Critical), with
rule key `validation:<Machine|Process>:<subject>:<type>`, pointing at the protocol. As with the other
rules, an open suggestion is not raised again, and a resolved one reopens when the rule finds it
again. FoaMES does not stop a machine or hold material because a qualification lapsed: people act on
the suggestion.

## Continued process verification

Stage 3 has two parts in FoaMES. The SPC rules in [spc.md](spc.md) watch every measurement all the
time and raise suggestions on signals. A **CPV** protocol is the periodic, approved review: for
example a quarterly execution with Capability and Statistical Control criteria over the quarter's
readings of each critical parameter.

## Code

| Module | Holds |
| --- | --- |
| `foames/foames_validation/qualification.py` | The rules, with no Frappe dependency: protocol types and their order, criterion evaluation, execution outcome, validity, status, findings |
| `foames/foames_mes/spc.py` | `capability`: Cp, Cpk, Pp, Ppk |
| `foames/foames_validation/doctype/` | Validation Protocol (+ Validation Acceptance Criterion), Validation Execution (+ Validation Result) |
| `foames/foames_validation/api.py` | Status per subject, `get_qualification_status` |
| `foames/foames_validation/tasks.py` | The daily requalification check |
| `foames/foames_validation/commissioning.py` | Opens the IQ when a commissioning package is handed over |
| `foames/foames_validation/report/qualification_status/` | The Qualification Status report |

## Implicit validation

For checks that run before and after a configuration change, sandbox promotion or on a schedule, with hashed evidence that gates read by ID, see [implicit-validation.md](implicit-validation.md). It reuses the capability and control rules above and does not replace a formal execution.
