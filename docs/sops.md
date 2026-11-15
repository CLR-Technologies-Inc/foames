# Standard operating procedures

FoaMES keeps standard operating procedures (SOPs) as controlled documents: each one is identified, reviewed and signed before use, the version in force is the only one offered at the machine, replaced versions are withdrawn, every change is recorded with its reason, and the people who work under an SOP are trained on the version in force. This is ordinary document control as ISO 9001 clause 7.5 and good manufacturing practice describe it.

An SOP says *what* is done and *who* is responsible. Step-by-step execution at a station, with data capture and sign-off per step, is the job of work instructions; a work instruction can name the SOP that governs it.

## Revisions

Every revision of an SOP is its own **Standard Operating Procedure** record, named `<code>-R<revision>`, for example `SOP-PRS-004-R3`. All revisions share the **SOP Code**. A revision moves through these states:

| Status | Meaning | How it gets there |
| --- | --- | --- |
| Draft | Being written. The only state in which the content can be edited. | Created, or sent back by a reviewer |
| In Review | Content fixed, waiting for signatures | **Send for Review** |
| Approved | Fully signed, waiting for its Effective On date | The last signature, when Effective On is in the future |
| Effective | The version in force | The last signature (Effective On empty or today or earlier), or the daily check on the Effective On date |
| Superseded | Replaced by a later revision | The next revision becoming Effective |
| Obsolete | Withdrawn with no replacement | **Retire**, with a reason |

A code has at most one Effective revision and at most one revision in progress (Draft, In Review or Approved) at a time. Superseded and Obsolete are final.

Once a revision has left Draft, its content, applicability, sign-off roles and training settings cannot be edited; saving such a change is refused with the list of fields. To change an Effective SOP, press **New Revision**: FoaMES copies it to a Draft numbered next, which supersedes the Effective revision when it in turn becomes Effective. From revision 2 a **Change Summary** is required before review.

## Setting up an SOP

Open **Standard Operating Procedure** and fill in:

- **SOP Code**: the document number all revisions share. Letters, digits and `. _ / -`; it is stored in upper case.
- **Title**, **Category** (Operations, Quality, Safety, Maintenance, Engineering, Other) and **Document Owner**, who keeps it current and leads its periodic review.
- **Purpose**, **Scope**, **Responsibilities**, **Procedure** (required) and **References**. If the controlled copy is a file, attach it as **Controlled Copy**.
- **Applies To**: where the SOP applies. A row names a **Machine**, a **Line** (every machine on it) or a **Process Reference**, an External Reference to an operation, routing step or workstation in the ERP (FoaMES never links ERP records directly). Leave the table empty for a site-wide SOP.
- **Approvals**: one row per sign-off, each a **Role** and its **Meaning** (Reviewed, Approved, Quality Approved).
- **Effective On**: leave empty to take effect on approval, or set a date to give people time to train first.
- **Review Every (Months)**: the periodic review interval, 12 by default, 0 for none.
- **Requires Acknowledgement**, **Training Roles** and **Acknowledge Within (Days)**: who must read and acknowledge each new revision, and how long they have.

## Sign-off

**Send for Review** fixes the content. Each approval row is then signed with **Sign** by a user who holds its role. The rules:

- The author of the revision (Prepared By) cannot sign it.
- One person signs at most one row of a revision, so a two-row sign-off always takes two people besides the author.
- Each signature records the user, the time, the role, the meaning and an optional comment. Signatures cannot be written by editing the record.
- **Reject** (by a holder of one of the sign-off roles, or anyone who may edit the SOP) sends the revision back to Draft with every signature cleared, and puts the reason on the record's timeline.

The signatures are an audit trail. They are not a validated 21 CFR Part 11 electronic signature: a site that needs one adds re-authentication at signing and validates its own installation.

## Training and acknowledgement

When an SOP requires acknowledgement, every enabled user holding one of its training roles must acknowledge each new revision:

- **Acknowledge** (under Training on the form): the current user has read and understood the Effective revision.
- **Record Training**: a trainer (FoaMES Quality, Supervisor or Engineer) records that someone was **Trained** or **Trained and Assessed**, with a note.

Each is an **SOP Acknowledgement** record holding the SOP revision, its code and revision number, the user, the method, the time and who recorded it. Only the Effective revision can be acknowledged. A person's status on an SOP is:

| Status | Meaning |
| --- | --- |
| Current | Acknowledged this revision |
| Outdated | Acknowledged an earlier revision of the same code only |
| Missing | Never acknowledged it |

The **SOP Training Matrix** report lists every Effective SOP that requires acknowledgement against every person who must acknowledge it, worst first, with the revision they acknowledged, when and how, the due date, and whether they are overdue. Filter by SOP code, category, user or status. The summary shows the share trained and the counts outdated, missing and overdue.

In line with the rule that agents suggest and people act, FoaMES does not stop anyone working on a machine because of a training gap. It reports the gap: on the matrix, through `operator_sop_gaps` (below) for the floor or an agent, and as a suggestion.

## The daily check

`check_sops` runs daily. It:

1. makes every Approved revision whose Effective On has come Effective, and supersedes the revision it replaces (closing that revision's open suggestions);
2. refreshes **Next Review On** and **Review Status** (Current, Review Due Soon within 30 days, Review Overdue) of every Effective revision;
3. raises an **Agent Suggestion** (category Quality) when a review is due soon (Info) or overdue (Warning), once per review date and status;
4. raises one Agent Suggestion (Warning) per revision when its acknowledgement period has passed and people in its training roles have still not acknowledged it, listing them in the evidence; it is marked Done once everyone has.

**Record Periodic Review** on an Effective revision records that the review found it still right: Last Reviewed On becomes today, the review interval restarts from there and the open review suggestions are marked Done. If the review finds it needs to change, start a new revision instead.

## Who can do what

| Role | Standard Operating Procedure | Sign | SOP Acknowledgement | Training Matrix |
| --- | --- | --- | --- | --- |
| FoaMES Engineer, FoaMES Quality, System Manager | Create, edit drafts, send for review, new revision, retire, record review | When they hold a sign-off role | Record training for others; read | Run |
| FoaMES Supervisor | Read | When they hold a sign-off role | Record training for others; read | Run |
| FoaMES Operator, FoaMES Maintenance | Read | When they hold a sign-off role | Acknowledge for themselves; read | No |

## For integrators

- `foames.foames_mes.sop` holds the rules (lifecycle transitions, sign-off eligibility, review dates, training status, applicability, the suggestions) with no Frappe dependency.
- Whitelisted in `foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure`:
  - `get_effective_sops(machine=None)`: the Effective SOPs, or those that apply at a machine (site-wide ones included).
  - `operator_sop_gaps(user=None, machine=None)`: the Effective SOPs at a machine that the user must acknowledge and has not, each with Missing or Outdated. Asking about another user needs FoaMES Quality, Supervisor or Engineer.
  - `submit_for_review`, `sign`, `reject`, `new_revision`, `retire`, `record_review`, `acknowledge`, `record_training`: the form's actions, POST only.
- A work instruction or any other record can cite its governing SOP with a Link to **Standard Operating Procedure**; link the revision, or store the SOP Code and look up the Effective revision with `get_effective_sops`.
