# Process FMEA

FoaMES keeps process failure mode and effects analyses (PFMEA) next to the floor data they are about, and checks them against that data. The method follows the AIAG and VDA FMEA Handbook (first edition, 2019): each failure chain is rated for severity, occurrence and detection, and ranked by **action priority** rather than by multiplying the ratings. The older Risk Priority Number is shown alongside for plants that still report it.

What FoaMES adds to a spreadsheet FMEA is the loop back from the floor. Once a PFMEA is released, FoaMES reads, every day, how often each failure actually happened on its machine and whether the characteristic it controls is signalling on SPC, and asks the FMEA team to review a rating when the floor disagrees with it. Ratings are never changed automatically: re-rating is the team's decision.

## The records

**PFMEA** (FoaMES Quality workspace, Quality card) is one analysis, usually one process or line. The header holds the title, process or line, product, status, revision, process responsibility, scope, team and dates (the planning step of the handbook). Status runs Draft, In Review, Released, Obsolete. Only Released PFMEAs are observed and raise suggestions; Obsolete ones drop out of the reports.

Each row of the **Failure Modes** table (a **PFMEA Item**) is one failure chain at one process step:

| Section | Fields | Handbook step |
| --- | --- | --- |
| Structure | Op, Process Step, Machine, Work Element (Man, Machine, Material, Method, Measurement, Environment) | 2 Structure analysis |
| Function | Process Function and Requirement, Special Characteristic (CC or SC), Specification / Tolerance | 3 Function analysis |
| Failure Chain | Failure Effect with Severity (S), Failure Mode, Failure Cause | 4 Failure analysis |
| Current Controls and Risk | Prevention Controls with Occurrence (O), Detection Controls with Detection (D), Action Priority, RPN | 5 Risk analysis |
| Control Plan | SPC Measurement, Sample Size / Frequency, Reaction Plan | Link to the control plan |
| Observed on the Floor | Scrap Counter, Downtime Reason, then what FoaMES observed | Occurrence check |
| Optimization | Prevention Action, Detection Action, Responsible, Target Date, Action Status, Completion Date, Action Taken / Evidence, revised S, O and D with the revised action priority | 6 Optimization |

Ratings are whole numbers from 1 to 10 and may be left empty while a PFMEA is a draft. Releasing it needs S, O and D on every row.

The action statuses are the handbook's: Open, Decision Pending, Implementation Pending, Completed, Not Implemented. A Completed action needs its completion date and the revised severity, occurrence and detection. Not Implemented needs the reason in Action Taken, which is how a High priority row records the decision not to act.

## Action priority

FoaMES computes the action priority of each row from its S, O and D (and the revised priority from the revised ratings) with the handbook's table. Severity comes first, then occurrence, then detection:

| Severity | Occurrence | D 7-10 | D 5-6 | D 2-4 | D 1 |
| --- | --- | --- | --- | --- | --- |
| 9-10 | 8-10 | H | H | H | H |
| 9-10 | 6-7 | H | H | H | H |
| 9-10 | 4-5 | H | H | H | M |
| 9-10 | 2-3 | H | M | L | L |
| 7-8 | 8-10 | H | H | H | H |
| 7-8 | 6-7 | H | H | H | M |
| 7-8 | 4-5 | H | M | M | M |
| 7-8 | 2-3 | M | M | L | L |
| 4-6 | 8-10 | H | H | M | M |
| 4-6 | 6-7 | M | M | M | L |
| 4-6 | 4-5 | M | L | L | L |
| 2-3 | 8-10 | M | M | L | L |
| any | 1 | L | L | L | L |

Every other combination, and severity 1, is Low. High means an action must be identified or the decision not to act justified; Medium means an action should be identified; Low means one could be. The header counts the rows at each priority and the actions still open.

## Observed occurrence

For a row with a **Machine** and either a **Scrap Counter** or a **Downtime Reason**, FoaMES counts incidents over the PFMEA's **Observe Last (Days)** window (default 90):

- **Units produced**: good plus scrap on the machine, from the counter deltas, the same way OEE and the maintenance meters count production.
- **Incidents**: the deltas on the row's scrap counter (a counter that counts only this failure, such as `reject_unseated`, not the machine's general `scrap`), plus one per Downtime Record on the machine with the row's reason.

Incidents per thousand units map to the occurrence rating the floor supports, with the incidents-per-thousand scale published in the AIAG PFMEA manual (fourth edition) and offered as an alternative occurrence table in the AIAG-VDA handbook:

| Incidents per thousand | Occurrence |
| --- | --- |
| 100 or more (1 in 10) | 10 |
| 50 (1 in 20) | 9 |
| 20 (1 in 50) | 8 |
| 10 (1 in 100) | 7 |
| 2 (1 in 500) | 6 |
| 0.5 (1 in 2,000) | 5 |
| 0.1 (1 in 10,000) | 4 |
| 0.01 (1 in 100,000) | 3 |
| fewer | 2 |

Occurrence 1 means the cause is prevented by design, which no observed rate can show, so an observed rate never maps below 2. With no production in the window there is no rate and no observed occurrence.

For a row with an **SPC Measurement**, FoaMES counts the SPC suggestions raised or re-raised on that measurement in the window (on the row's machine, or on any machine when the row has none). See [spc.md](spc.md) for how SPC signals are found.

The results are stored on the row (Units Produced, Incidents, Incidents per Thousand, Observed Occurrence, SPC Signals, Observed On) and the time on the header (Last Observed). **Observe Floor Now** on the form reads them at once; it needs write permission on the PFMEA.

## The daily check

`foames.foames_mes.tasks.check_pfmeas` runs daily. It observes every Released PFMEA and raises Agent Suggestions (category Quality, agent `foames-pfmea`, reference the PFMEA):

| Raised when | Severity | Rule key |
| --- | --- | --- |
| The observed occurrence is above the rated occurrence | Critical when the priority at the observed occurrence is High, otherwise Warning | `pfmea:<pfmea>:<row>:occurrence:<observed>` |
| The row's SPC measurement signalled in the window | Critical for severity 9 or 10, otherwise Warning | `pfmea:<pfmea>:<row>:spc` |
| The row is High priority with no prevention or detection action and no Not Implemented decision | Warning | `pfmea:<pfmea>:<row>:high-without-action` |
| An action is past its target date and not Completed or Not Implemented | Critical for a High row, otherwise Warning | `pfmea:<pfmea>:<row>:overdue:<target date>` |

`<row>` is the PFMEA Item's id, which stays the same while the row exists. An open suggestion is not raised twice. A dismissed occurrence suggestion stays dismissed while the observed rating stays the same, and a higher observed rating raises a new one. A dismissed SPC suggestion stays dismissed until the measurement signals again. Moving a target date raises a fresh overdue suggestion only if the new date passes too.

## Reports

- **PFMEA Risk Register**: every failure chain across the PFMEAs you can read, High first, then by severity, occurrence and detection, with what the floor observed and the state of each action. Filters: PFMEA, process, machine, action priority, open actions only. Observed occurrences above the rating are marked red.
- **PFMEA Control Plan**: the control plan the PFMEA implies, one line per chain in operation order: the characteristic and its class, the specification, the prevention controls as the control method, the detection controls as the evaluation technique, the SPC measurement, the sample size and frequency, and the reaction plan. Filters: PFMEA, process, machine, special characteristics only.

Both leave Obsolete PFMEAs out unless one is chosen. The form has buttons for both under **View**.

## Permissions

FoaMES Quality and FoaMES Engineer create and edit PFMEAs. Supervisors, operators and maintenance read them and the reports.
