# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Phase Review Discipline (PRD): the governance of how an NPI program goes to market. No Frappe
dependency.

The stage gates in `npi` say what has to be done in each stage. The phase review discipline says
who decides and how: a phase review board with named roles holds a formal phase review at each
gate, checks the entry criteria (is the program ready to be reviewed?) and the exit criteria (has
the stage achieved what it must?), records attendance, votes, the decision, its conditions, the
minutes and the action items, and only then does the program move. The pattern is the phase
review process of PACE (Product And Cycle-time Excellence, PRTM; M. E. McGrath, Setting the PACE
in Product Development) and of Cooper's stage-gate, with launch readiness and go-to-market
criteria at the last gates.

Board roles:

- Chair: holds decision authority; records the decision after hearing the board.
- Member: votes.
- Advisor and Secretary: attend and are recorded, do not vote.

A review can be closed with a decision only when the Chair is present, the voting members present
reach the board's quorum, the stage's entry criteria are met, and for Go or Conditional Go the
exit criteria are met as well (on top of the required deliverables the gate rules in `npi` check).
Votes are recorded; the Chair decides, and a decision against the majority needs a rationale.
"""

from __future__ import annotations

from foames.foames_life_sciences.npi import DECISIONS, PASSING, STAGES

BOARD_ROLES = ("Chair", "Member", "Advisor", "Secretary")
VOTING_ROLES = ("Chair", "Member")
VOTES = (*DECISIONS, "Abstain")
CRITERION_KINDS = ("Entry", "Exit")
REVIEW_TYPES = ("Phase Review", "Launch Readiness Review", "Post-Launch Review")
DEFAULT_QUORUM = 3

# The review type each gate usually is: the Transfer gate decides whether the product is ready to
# go to market; the Launch gate is the post-launch review that closes the program.
REVIEW_TYPE_FOR_STAGE = {stage: "Phase Review" for stage in STAGES}
REVIEW_TYPE_FOR_STAGE["Transfer"] = "Launch Readiness Review"
REVIEW_TYPE_FOR_STAGE["Launch"] = "Post-Launch Review"

# (stage, kind, criterion). Entry criteria: is the program ready to be reviewed. Exit criteria:
# has the stage achieved what the next one depends on, including the go-to-market criteria.
CRITERIA_TEMPLATE: tuple[tuple[str, str, str], ...] = (
	("Concept", "Entry", "Phase review package issued to the board before the review"),
	("Concept", "Exit", "Market need, target customer and intended use agreed"),
	("Concept", "Exit", "Business case and preliminary funding approved"),
	("Concept", "Exit", "Core team and program lead appointed"),
	("Feasibility", "Entry", "Phase review package issued to the board before the review"),
	("Feasibility", "Exit", "Technical feasibility shown; key risks have a mitigation plan"),
	("Feasibility", "Exit", "Requirements baselined"),
	("Feasibility", "Exit", "Updated business case, schedule and budget for development"),
	("Development", "Entry", "Phase review package issued to the board before the review"),
	("Development", "Exit", "Design frozen for verification; open design changes are controlled"),
	("Development", "Exit", "Manufacturing process defined at the intended scale; make-or-buy decided"),
	("Development", "Exit", "Cost of goods estimate within the business case"),
	("Verification & Validation", "Entry", "Phase review package issued to the board before the review"),
	("Verification & Validation", "Exit", "Verification and validation complete with no open critical issue"),
	("Verification & Validation", "Exit", "Regulatory submission filed or path confirmed"),
	("Verification & Validation", "Exit", "Commercial plan drafted: pricing, channels, forecast"),
	("Transfer", "Entry", "Phase review package issued to the board before the review"),
	("Transfer", "Exit", "Regulatory clearance or approval to market received"),
	(
		"Transfer",
		"Exit",
		"Manufacturing ready: process validated, capacity and supply secured for the forecast",
	),
	("Transfer", "Exit", "Go-to-market ready: launch plan, pricing, labeling, channel and sales training"),
	("Transfer", "Exit", "Service, complaint handling, pharmacovigilance or vigilance ready"),
	("Transfer", "Exit", "Launch stock built and released"),
	("Launch", "Entry", "Post-launch data collected over the agreed period"),
	("Launch", "Exit", "Launch targets reviewed: volume, cost, quality, customer feedback"),
	("Launch", "Exit", "Product handed over to the sustaining organisation; lessons learned recorded"),
)


def criteria_template() -> list[tuple[str, str, str]]:
	return list(CRITERIA_TEMPLATE)


def unmet_criteria(criteria: list[dict], stage: str, kind: str) -> list[str]:
	"""Required criteria of this stage and kind that are not met."""
	return [
		c["criterion"]
		for c in criteria
		if c.get("stage") == stage and c.get("kind") == kind and c.get("required", True) and not c.get("met")
	]


def board_problems(members: list[dict], quorum: int) -> list[str]:
	problems = []
	users = [m.get("user") for m in members]
	if len(users) != len(set(users)):
		problems.append("A person can sit on the board only once")
	chairs = [m for m in members if m.get("board_role") == "Chair"]
	if len(chairs) != 1:
		problems.append("The board needs exactly one Chair, who holds decision authority")
	voting = [m for m in members if m.get("board_role") in VOTING_ROLES]
	if quorum < 1:
		problems.append("The quorum must be at least 1")
	elif quorum > len(voting):
		problems.append(f"The quorum ({quorum}) is larger than the voting members ({len(voting)})")
	return problems


def tally(attendees: list[dict]) -> dict:
	"""Votes of the voting members present, and the majority decision (None on a tie or no votes)."""
	counts: dict[str, int] = {}
	for a in attendees:
		if (
			a.get("present")
			and a.get("board_role") in VOTING_ROLES
			and a.get("vote")
			and a["vote"] != "Abstain"
		):
			counts[a["vote"]] = counts.get(a["vote"], 0) + 1
	majority = None
	if counts:
		top = max(counts.values())
		leaders = [v for v, n in counts.items() if n == top]
		majority = leaders[0] if len(leaders) == 1 else None
	return {"counts": counts, "majority": majority}


def review_problems(
	*,
	stage: str,
	decision: str | None,
	attendees: list[dict],
	quorum: int,
	criteria: list[dict],
	decided_by: str | None,
	rationale: str | None = None,
) -> list[str]:
	"""Every reason a phase review cannot be closed with this decision; empty when it can."""
	problems = []
	if decision not in DECISIONS:
		return ["Record the board's decision: Go, Conditional Go, Recycle, Hold or Kill"]
	present = [a for a in attendees if a.get("present")]
	chair = next((a for a in attendees if a.get("board_role") == "Chair"), None)
	if not chair or not chair.get("present"):
		problems.append("The Chair, who holds decision authority, is not recorded as present")
	elif decided_by and chair.get("user") != decided_by:
		problems.append("Only the Chair of the board closes the review with the decision")
	voting_present = [a for a in present if a.get("board_role") in VOTING_ROLES]
	if len(voting_present) < quorum:
		problems.append(f"No quorum: {len(voting_present)} voting members present, {quorum} needed")
	missing_votes = [a.get("user") for a in voting_present if not a.get("vote")]
	if missing_votes:
		problems.append(
			"Voting members present without a recorded vote: "
			+ ", ".join(str(user) for user in missing_votes)
		)
	entry = unmet_criteria(criteria, stage, "Entry")
	if entry:
		problems.append("Entry criteria not met: " + "; ".join(entry))
	if decision in PASSING:
		exit_ = unmet_criteria(criteria, stage, "Exit")
		if exit_:
			problems.append("Exit criteria not met: " + "; ".join(exit_))
	majority = tally(attendees)["majority"]
	if majority and majority != decision and not (rationale or "").strip():
		problems.append(
			f"The decision differs from the board's majority vote ({majority}); record the rationale"
		)
	return problems


def action_findings(review: dict, actions: list[dict], today) -> list[dict]:
	"""Suggestions for action items of a closed phase review that are past their due date."""
	out = []
	for a in actions:
		if a.get("status") == "Open" and a.get("due_date") and a["due_date"] < today:
			out.append(
				{
					"rule_key": f"phase-review-action:{review['name']}:{a.get('idx')}:{a['due_date']}",
					"title": f"{review['name']}: action past due",
					"category": "Other",
					"severity": "Info",
					"suggestion": (
						f"The {review.get('stage')} phase review of {review.get('npi_program')} set an action due "
						f"{a['due_date']}, still open: {a.get('action')}"
						+ (f" (owner {a['owner_user']})" if a.get("owner_user") else "")
					),
					"evidence": {
						"action": a.get("action"),
						"due_date": str(a["due_date"]),
						"owner": a.get("owner_user"),
					},
				}
			)
	return out
